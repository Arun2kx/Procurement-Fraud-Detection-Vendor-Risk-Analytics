"""Self-approval and purchase-order authority checks."""

from __future__ import annotations

import pandas as pd

from src.fraud_detection.common import candidates_frame, evidence, rule_fields


def find_self_approvals(
    approvals: pd.DataFrame,
    purchase_orders: pd.DataFrame,
    expenses: pd.DataFrame,
) -> pd.DataFrame:
    """Flag approved records where the approver is the requestor or claimant."""
    owners: dict[tuple[str, str], str] = {}
    amounts: dict[tuple[str, str], float] = {}
    vendors: dict[tuple[str, str], str] = {}
    for _, row in purchase_orders.iterrows():
        key = ("purchase_order", str(row["po_id"]))
        owners[key] = str(row["requestor_employee_id"])
        amounts[key] = float(row["po_amount_inr"])
        vendors[key] = str(row["vendor_id"])
    for _, row in expenses.iterrows():
        key = ("employee_expense", str(row["expense_id"]))
        owners[key] = str(row["employee_id"])
        amounts[key] = float(row["amount_inr"]) if pd.notna(row["amount_inr"]) else 0.0
    base = rule_fields("SELF_APPROVAL")
    rows: list[dict] = []
    approved = approvals[approvals["decision"] == "Approved"]
    for _, row in approved.sort_values("approval_id").iterrows():
        key = (str(row["entity_type"]), str(row["entity_id"]))
        owner = owners.get(key)
        if not owner or owner != str(row["approver_employee_id"]):
            continue
        payload = {
            "approval_id": str(row["approval_id"]),
            "entity_type": str(row["entity_type"]),
            "entity_id": str(row["entity_id"]),
            "approver_employee_id": str(row["approver_employee_id"]),
            "owner_employee_id": owner,
        }
        rows.append(
            {
                **base,
                "entity_id": str(row["approval_id"]),
                "vendor_id": vendors.get(key, ""),
                "employee_id": owner,
                "estimated_exposure_inr": round(amounts.get(key, 0.0), 2),
                "detection_reason": "The approver is the same employee who requested the purchase or submitted the claim.",
                "supporting_evidence": evidence(payload),
            }
        )
    return candidates_frame(rows)


def find_po_approval_issues(
    purchase_orders: pd.DataFrame,
    approvals: pd.DataFrame,
    employees: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """Flag missing approvals and approvals above the approver's limit.

    Rejected purchase orders are not treated as missing approvals. A purchase
    order with an approval decision is not counted as missing, even when the
    approver's limit is too low; that case is a limit breach.
    """
    required_above = float(config["thresholds"]["approval_required_above_inr"])
    limits = employees.set_index("employee_id")["approval_limit_inr"]
    po_approvals = approvals[approvals["entity_type"] == "purchase_order"].copy()
    rows: list[dict] = []
    missing = rule_fields("PO_MISSING_APPROVAL")
    breach = rule_fields("PO_APPROVAL_LIMIT_BREACH")
    for _, order in purchase_orders.sort_values("po_id").iterrows():
        if str(order["status"]) not in {"Approved", "Closed"}:
            continue
        amount = float(order["po_amount_inr"])
        if pd.isna(amount) or amount < required_above:
            continue
        related = po_approvals[po_approvals["entity_id"] == order["po_id"]]
        if related.empty:
            payload = {
                "po_id": str(order["po_id"]),
                "po_amount_inr": round(amount, 2),
                "requestor_employee_id": str(order["requestor_employee_id"]),
                "vendor_id": str(order["vendor_id"]),
            }
            rows.append(
                {
                    **missing,
                    "entity_id": str(order["po_id"]),
                    "vendor_id": str(order["vendor_id"]),
                    "employee_id": str(order["requestor_employee_id"]),
                    "estimated_exposure_inr": round(amount, 2),
                    "detection_reason": "Approved purchase order at or above the approval threshold has no approval record.",
                    "supporting_evidence": evidence(payload),
                }
            )
            continue
        approved = related[related["decision"] == "Approved"]
        if approved.empty:
            continue
        approver_limits = approved["approver_employee_id"].map(limits)
        max_limit = float(approver_limits.max()) if approver_limits.notna().any() else 0.0
        if max_limit < amount:
            payload = {
                "po_id": str(order["po_id"]),
                "po_amount_inr": round(amount, 2),
                "max_approver_limit_inr": round(max_limit, 2),
                "approver_employee_ids": [str(value) for value in approved["approver_employee_id"]],
            }
            rows.append(
                {
                    **breach,
                    "entity_id": str(order["po_id"]),
                    "vendor_id": str(order["vendor_id"]),
                    "employee_id": str(order["requestor_employee_id"]),
                    "estimated_exposure_inr": round(amount, 2),
                    "detection_reason": "The highest limit among employees who approved the order is below the order value.",
                    "supporting_evidence": evidence(payload),
                }
            )
    return candidates_frame(rows)
