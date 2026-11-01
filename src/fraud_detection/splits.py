"""Split-purchase and near-threshold purchase screening."""

from __future__ import annotations

import pandas as pd

from src.fraud_detection.common import candidates_frame, evidence, rule_fields
from src.utils.grouping import UnionFind


def _po_dates(purchase_orders: pd.DataFrame) -> pd.DataFrame:
    frame = purchase_orders.copy()
    frame["po_date"] = pd.to_datetime(frame["po_date"])
    frame["po_amount_inr"] = pd.to_numeric(frame["po_amount_inr"], errors="coerce")
    return frame


def _max_approver_limit(
    po_ids: list[str],
    approvals: pd.DataFrame,
    employees: pd.DataFrame,
) -> float:
    approved = approvals[
        (approvals["entity_type"] == "purchase_order")
        & (approvals["decision"] == "Approved")
        & (approvals["entity_id"].isin(po_ids))
    ]
    if approved.empty:
        return 0.0
    limits = employees.set_index("employee_id")["approval_limit_inr"]
    approver_limits = approved["approver_employee_id"].map(limits)
    if approver_limits.dropna().empty:
        return 0.0
    return float(approver_limits.max())


def find_split_purchase_clusters(
    purchase_orders: pd.DataFrame,
    approvals: pd.DataFrame,
    employees: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """Group sub-threshold orders that together cross the approval threshold.

    A cluster is alerted only when nobody who approved a member had a limit
    covering the combined value. Clusters with sufficient authority are kept
    in the output with disposition ``adequate_approval``.
    """
    threshold = float(config["thresholds"]["split_approval_threshold_inr"])
    window_days = int(config["thresholds"]["split_window_days"])
    minimum = int(config["thresholds"]["split_min_transactions"])
    orders = _po_dates(purchase_orders)
    eligible = orders[orders["po_amount_inr"] < threshold].copy()
    output_rows: list[dict] = []

    for (vendor_id, department, category), group in eligible.groupby(
        ["vendor_id", "department", "category"], sort=True
    ):
        records = group.sort_values(["po_date", "po_id"]).to_dict("records")
        union = UnionFind()
        for record in records:
            union.add(str(record["po_id"]))
        for left_index, left in enumerate(records):
            for right in records[left_index + 1 :]:
                gap = abs((right["po_date"] - left["po_date"]).days)
                if gap <= window_days:
                    union.union(str(left["po_id"]), str(right["po_id"]))
        for members in union.groups():
            if len(members) < minimum:
                continue
            member_rows = group[group["po_id"].astype(str).isin(members)]
            cluster_sum = round(float(member_rows["po_amount_inr"].sum()), 2)
            if cluster_sum < threshold:
                continue
            max_limit = round(_max_approver_limit(members, approvals, employees), 2)
            disposition = "insufficient_approval" if max_limit < cluster_sum else "adequate_approval"
            cluster_id = "SPC-" + members[0]
            for _, row in member_rows.sort_values(["po_date", "po_id"]).iterrows():
                output_rows.append(
                    {
                        "cluster_id": cluster_id,
                        "po_id": row["po_id"],
                        "vendor_id": vendor_id,
                        "department": department,
                        "category": category,
                        "po_date": pd.Timestamp(row["po_date"]).date().isoformat(),
                        "po_amount_inr": round(float(row["po_amount_inr"]), 2),
                        "cluster_sum_inr": cluster_sum,
                        "max_approver_limit_inr": max_limit,
                        "disposition": disposition,
                    }
                )

    columns = [
        "cluster_id",
        "po_id",
        "vendor_id",
        "department",
        "category",
        "po_date",
        "po_amount_inr",
        "cluster_sum_inr",
        "max_approver_limit_inr",
        "disposition",
    ]
    if not output_rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(output_rows).sort_values(["cluster_id", "po_date", "po_id"]).reset_index(drop=True)


def split_alerts(clusters: pd.DataFrame) -> pd.DataFrame:
    """Turn insufficient-approval clusters into one alert per purchase order."""
    if clusters.empty:
        return candidates_frame([])
    flagged = clusters[clusters["disposition"] == "insufficient_approval"]
    base = rule_fields("SPLIT_PURCHASE")
    rows: list[dict] = []
    for cluster_id, group in flagged.groupby("cluster_id", sort=True):
        ordered = group.sort_values(["po_date", "po_id"])
        anchor = str(ordered.iloc[0]["po_id"])
        cluster_sum = float(ordered.iloc[0]["cluster_sum_inr"])
        payload = {
            "cluster_id": cluster_id,
            "po_ids": [str(value) for value in ordered["po_id"]],
            "po_amounts_inr": [float(value) for value in ordered["po_amount_inr"]],
            "cluster_sum_inr": cluster_sum,
            "max_approver_limit_inr": float(ordered.iloc[0]["max_approver_limit_inr"]),
            "vendor_id": str(ordered.iloc[0]["vendor_id"]),
            "department": str(ordered.iloc[0]["department"]),
            "category": str(ordered.iloc[0]["category"]),
        }
        for _, row in ordered.iterrows():
            rows.append(
                {
                    **base,
                    "entity_id": str(row["po_id"]),
                    "vendor_id": str(row["vendor_id"]),
                    "employee_id": "",
                    "estimated_exposure_inr": cluster_sum if str(row["po_id"]) == anchor else 0.0,
                    "detection_reason": (
                        "Sub-threshold purchase orders for the same vendor, department, and category "
                        "combine above the approval threshold without an approver authorised for the combined value."
                    ),
                    "supporting_evidence": evidence(payload),
                }
            )
    return candidates_frame(rows)


def find_threshold_gaming(purchase_orders: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Flag vendors with repeated purchase orders just below the approval threshold."""
    threshold = float(config["thresholds"]["split_approval_threshold_inr"])
    ratio = float(config["thresholds"]["near_threshold_ratio"])
    window_days = int(config["thresholds"]["threshold_gaming_window_days"])
    minimum = int(config["thresholds"]["threshold_gaming_min_count"])
    low = threshold * ratio
    orders = _po_dates(purchase_orders)
    band = orders[(orders["po_amount_inr"] >= low) & (orders["po_amount_inr"] < threshold)].copy()
    flagged: dict[str, dict] = {}
    for vendor_id, group in band.groupby("vendor_id", sort=True):
        records = group.sort_values(["po_date", "po_id"]).to_dict("records")
        left = 0
        for right, record in enumerate(records):
            while (record["po_date"] - records[left]["po_date"]).days > window_days:
                left += 1
            if right - left + 1 >= minimum:
                for member in records[left : right + 1]:
                    flagged[str(member["po_id"])] = member | {"vendor_id": vendor_id}

    base = rule_fields("THRESHOLD_GAMING")
    rows: list[dict] = []
    by_vendor: dict[str, list[dict]] = {}
    for record in flagged.values():
        by_vendor.setdefault(str(record["vendor_id"]), []).append(record)
    for vendor_id, members in sorted(by_vendor.items()):
        ordered = sorted(members, key=lambda item: (item["po_date"], item["po_id"]))
        anchor = str(ordered[0]["po_id"])
        total = round(sum(float(item["po_amount_inr"]) for item in ordered), 2)
        payload = {
            "vendor_id": vendor_id,
            "po_ids": [str(item["po_id"]) for item in ordered],
            "po_amounts_inr": [round(float(item["po_amount_inr"]), 2) for item in ordered],
            "threshold_inr": threshold,
            "band_low_inr": round(low, 2),
            "window_days": window_days,
        }
        for item in ordered:
            rows.append(
                {
                    **base,
                    "entity_id": str(item["po_id"]),
                    "vendor_id": vendor_id,
                    "employee_id": str(item.get("requestor_employee_id", "")),
                    "estimated_exposure_inr": total if str(item["po_id"]) == anchor else 0.0,
                    "detection_reason": (
                        f"At least {minimum} purchase orders for this vendor fall between "
                        f"{ratio:.0%} and 100% of the {threshold:.0f} approval threshold inside {window_days} days."
                    ),
                    "supporting_evidence": evidence(payload),
                }
            )
    return candidates_frame(rows)
