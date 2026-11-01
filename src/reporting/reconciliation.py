"""Purchase-order, invoice, and payment reconciliation."""

from __future__ import annotations

import pandas as pd


def reconcile(tables: dict[str, pd.DataFrame], config: dict) -> pd.DataFrame:
    """Match committed, billed, and paid amounts.

    A difference within the configured rupee tolerance is treated as matched.
    Progress bills are compared as a group against their purchase order.
    """
    tolerance = float(config["thresholds"]["reconciliation_amount_tolerance_inr"])
    po_required = float(config["thresholds"]["po_required_above_inr"])
    orders = tables["purchase_orders"].drop_duplicates("po_id").copy()
    invoices = tables["invoices"].drop_duplicates("invoice_id").copy()
    payments = tables["payments"].drop_duplicates("payment_id").copy()
    for frame, column in (
        (orders, "po_amount_inr"),
        (invoices, "total_amount_inr"),
        (payments, "payment_amount_inr"),
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    invoices["po_id"] = invoices["po_id"].fillna("").astype(str).replace({"nan": ""})
    completed = payments[payments["status"] == "Completed"]
    invoice_pay = completed.groupby("invoice_id")["payment_amount_inr"].sum()
    po_invoice = (
        invoices[invoices["po_id"] != ""]
        .groupby("po_id")["total_amount_inr"]
        .sum()
    )
    rows = []
    for _, order in orders.iterrows():
        billed = float(po_invoice.get(order["po_id"], 0.0))
        linked = invoices[invoices["po_id"] == order["po_id"]]
        paid = float(linked["invoice_id"].map(invoice_pay).fillna(0).sum()) if not linked.empty else 0.0
        ordered_amount = float(order["po_amount_inr"])
        rows.append(
            {
                "record_type": "purchase_order",
                "record_id": order["po_id"],
                "vendor_id": order["vendor_id"],
                "po_amount_inr": round(ordered_amount, 2),
                "invoiced_amount_inr": round(billed, 2),
                "paid_amount_inr": round(paid, 2),
                "match_status": _po_status(ordered_amount, billed, paid, tolerance, str(order["status"])),
            }
        )
    for _, invoice in invoices.iterrows():
        total = float(invoice["total_amount_inr"]) if pd.notna(invoice["total_amount_inr"]) else 0.0
        paid = float(invoice_pay.get(invoice["invoice_id"], 0.0))
        po_id = str(invoice["po_id"])
        if po_id in {"", "nan"}:
            status = "Non-PO below threshold" if 0 < total < po_required else "Missing purchase order"
        elif po_id not in set(orders["po_id"].astype(str)):
            status = "Orphan purchase-order reference"
        else:
            status = _invoice_payment_status(total, paid, tolerance, str(invoice["status"]))
        rows.append(
            {
                "record_type": "invoice",
                "record_id": invoice["invoice_id"],
                "vendor_id": invoice["vendor_id"],
                "po_amount_inr": None,
                "invoiced_amount_inr": round(total, 2),
                "paid_amount_inr": round(paid, 2),
                "match_status": status,
            }
        )
    known_invoices = set(invoices["invoice_id"].astype(str))
    for _, payment in payments.iterrows():
        if str(payment["invoice_id"]) in known_invoices:
            continue
        rows.append(
            {
                "record_type": "payment",
                "record_id": payment["payment_id"],
                "vendor_id": payment["vendor_id"],
                "po_amount_inr": None,
                "invoiced_amount_inr": 0.0,
                "paid_amount_inr": round(float(payment["payment_amount_inr"]), 2) if pd.notna(payment["payment_amount_inr"]) else 0.0,
                "match_status": "Orphan payment",
            }
        )
    return pd.DataFrame(rows)


def _close(left: float, right: float, tolerance: float) -> bool:
    return abs(left - right) <= tolerance


def _po_status(ordered: float, billed: float, paid: float, tolerance: float, po_status: str) -> str:
    if po_status == "Rejected":
        return "Rejected purchase order"
    if billed == 0:
        return "Uninvoiced purchase order"
    if billed - ordered > tolerance:
        return "Invoiced above purchase order"
    if ordered - billed > tolerance:
        return "Partly invoiced"
    if _close(paid, billed, tolerance):
        return "Matched"
    if paid - billed > tolerance:
        return "Paid above invoice"
    if paid == 0:
        return "Invoiced and unpaid"
    return "Partly paid"


def _invoice_payment_status(total: float, paid: float, tolerance: float, status: str) -> str:
    if total < 0:
        return "Invalid invoice amount"
    if status == "Disputed" and paid == 0:
        return "Disputed and unpaid"
    if paid == 0:
        return "Unpaid"
    if paid - total > tolerance:
        return "Overpaid"
    if total - paid > tolerance:
        return "Underpaid"
    return "Payment matched"


def concentration(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Pareto vendor spend, category HHI, and department-month spend."""
    invoices = tables["invoices"].drop_duplicates("invoice_id").copy()
    vendors = tables["vendors"][["vendor_id", "vendor_category"]]
    orders = tables["purchase_orders"][["po_id", "department"]]
    invoices["total_amount_inr"] = pd.to_numeric(invoices["total_amount_inr"], errors="coerce").fillna(0)
    invoices["spend"] = invoices["total_amount_inr"].clip(lower=0)
    invoices["invoice_date"] = pd.to_datetime(invoices["invoice_date"], errors="coerce")
    merged = invoices.merge(vendors, on="vendor_id", how="left").merge(orders, on="po_id", how="left")
    vendor_spend = (
        merged.groupby(["vendor_id", "vendor_category"], as_index=False)["spend"]
        .sum()
        .sort_values("spend", ascending=False)
    )
    total = float(vendor_spend["spend"].sum())
    vendor_spend["spend_share"] = vendor_spend["spend"] / total if total else 0
    vendor_spend["cumulative_share"] = vendor_spend["spend_share"].cumsum()
    vendor_spend["pareto_within_80_percent"] = vendor_spend["cumulative_share"] <= 0.80
    vendor_spend["spend"] = vendor_spend["spend"].round(2)
    vendor_spend["spend_share"] = vendor_spend["spend_share"].round(6)
    vendor_spend["cumulative_share"] = vendor_spend["cumulative_share"].round(6)

    hhi_rows = []
    for category, group in vendor_spend.groupby("vendor_category"):
        category_total = float(group["spend"].sum())
        if category_total == 0:
            continue
        shares = group["spend"] / category_total
        hhi_rows.append(
            {
                "vendor_category": category,
                "vendor_count": int(len(group)),
                "spend_inr": round(category_total, 2),
                "hhi": round(float((shares ** 2).sum()), 6),
                "hhi_points": round(float((shares ** 2).sum() * 10000), 2),
            }
        )
    hhi = pd.DataFrame(hhi_rows).sort_values("hhi", ascending=False)
    department = merged.dropna(subset=["invoice_date"]).copy()
    department["department"] = department["department"].fillna("Non-PO")
    department["year_month"] = department["invoice_date"].dt.to_period("M").astype(str)
    monthly = (
        department.groupby(["department", "year_month"], as_index=False)["spend"]
        .sum()
        .rename(columns={"spend": "spend_inr"})
    )
    monthly["spend_inr"] = monthly["spend_inr"].round(2)
    return vendor_spend.reset_index(drop=True), hhi.reset_index(drop=True), monthly
