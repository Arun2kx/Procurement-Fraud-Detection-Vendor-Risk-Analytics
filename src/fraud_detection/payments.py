"""Payment duplicate, timing, and amount screening."""

from __future__ import annotations

import pandas as pd

from src.fraud_detection.common import candidates_frame, evidence, rule_fields


def find_payment_exceptions(
    payments: pd.DataFrame,
    invoices: pd.DataFrame,
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Screen completed payments against the related invoice.

    Duplicate detection requires two or more completed payments that each cover
    at least 98% of the invoice total. A single overpayment is a mismatch.
    Delayed-payment alerts ignore invoices already marked disputed.
    """
    tolerance = float(config["thresholds"]["payment_amount_tolerance"])
    delay_days = int(config["thresholds"]["payment_delay_alert_days"])
    invoice_index = invoices.drop_duplicates("invoice_id").set_index("invoice_id")
    completed = payments[payments["status"] == "Completed"].copy()
    completed["payment_date"] = pd.to_datetime(completed["payment_date"])
    completed["payment_amount_inr"] = pd.to_numeric(completed["payment_amount_inr"], errors="coerce")

    rows: list[dict] = []
    exception_rows: list[dict] = []
    for invoice_id, group in completed.groupby("invoice_id", sort=True):
        invoice_key = str(invoice_id)
        if invoice_key == "" or invoice_key not in invoice_index.index:
            continue
        invoice = invoice_index.loc[invoice_key]
        total = invoice["total_amount_inr"]
        if pd.isna(total) or float(total) <= 0:
            continue
        total = float(total)
        ordered = group.sort_values(["payment_date", "payment_id"])
        full = ordered[ordered["payment_amount_inr"] >= total * (1 - tolerance)]
        paid_sum = float(ordered["payment_amount_inr"].sum())
        invoice_date = pd.Timestamp(invoice["invoice_date"])
        due_date = pd.Timestamp(invoice["due_date"])
        disputed = bool(invoice["dispute_flag"])
        duplicate_ids = set(full["payment_id"].astype(str)) if len(full) >= 2 else set()

        if duplicate_ids:
            anchor = str(ordered[ordered["payment_id"].astype(str).isin(duplicate_ids)].iloc[0]["payment_id"])
            payload = {
                "invoice_id": invoice_key,
                "invoice_total_inr": round(total, 2),
                "payment_ids": [str(value) for value in ordered["payment_id"] if str(value) in duplicate_ids],
                "payment_amounts_inr": [
                    round(float(value), 2)
                    for value, payment_id in zip(ordered["payment_amount_inr"], ordered["payment_id"], strict=False)
                    if str(payment_id) in duplicate_ids
                ],
            }
            base = rule_fields("DUP_PAYMENT")
            for _, payment in ordered.iterrows():
                payment_id = str(payment["payment_id"])
                if payment_id not in duplicate_ids:
                    continue
                rows.append(
                    {
                        **base,
                        "entity_id": payment_id,
                        "vendor_id": str(payment["vendor_id"]),
                        "employee_id": "",
                        "estimated_exposure_inr": 0.0 if payment_id == anchor else round(float(payment["payment_amount_inr"]), 2),
                        "detection_reason": "More than one completed payment covers essentially the full invoice total.",
                        "supporting_evidence": evidence(payload),
                    }
                )
                exception_rows.append(_exception(payment, invoice_key, "DUP_PAYMENT", total, paid_sum))

        overpaid = paid_sum > total * (1 + tolerance)
        underpaid = str(invoice["status"]) == "Paid" and paid_sum < total * (1 - tolerance)
        if (overpaid or underpaid) and not duplicate_ids:
            base = rule_fields("PAYMENT_MISMATCH")
            payload = {
                "invoice_id": invoice_key,
                "invoice_total_inr": round(total, 2),
                "payment_sum_inr": round(paid_sum, 2),
                "payment_ids": [str(value) for value in ordered["payment_id"]],
            }
            anchor = str(ordered.iloc[0]["payment_id"])
            for _, payment in ordered.iterrows():
                payment_id = str(payment["payment_id"])
                rows.append(
                    {
                        **base,
                        "entity_id": payment_id,
                        "vendor_id": str(payment["vendor_id"]),
                        "employee_id": "",
                        "estimated_exposure_inr": round(abs(paid_sum - total), 2) if payment_id == anchor else 0.0,
                        "detection_reason": "Completed payments do not agree with the invoice total.",
                        "supporting_evidence": evidence(payload),
                    }
                )
                exception_rows.append(_exception(payment, invoice_key, "PAYMENT_MISMATCH", total, paid_sum))

        early_base = rule_fields("EARLY_PAYMENT")
        late_base = rule_fields("LATE_PAYMENT")
        for _, payment in ordered.iterrows():
            payment_date = pd.Timestamp(payment["payment_date"])
            if payment_date < invoice_date:
                payload = {
                    "invoice_id": invoice_key,
                    "invoice_date": invoice_date.date().isoformat(),
                    "payment_date": payment_date.date().isoformat(),
                    "payment_id": str(payment["payment_id"]),
                }
                rows.append(
                    {
                        **early_base,
                        "entity_id": str(payment["payment_id"]),
                        "vendor_id": str(payment["vendor_id"]),
                        "employee_id": "",
                        "estimated_exposure_inr": round(float(payment["payment_amount_inr"]), 2),
                        "detection_reason": "The payment date is earlier than the invoice date.",
                        "supporting_evidence": evidence(payload),
                    }
                )
                exception_rows.append(_exception(payment, invoice_key, "EARLY_PAYMENT", total, paid_sum))
            if pd.notna(due_date) and not disputed:
                days_late = (payment_date - due_date).days
                if days_late > delay_days:
                    payload = {
                        "invoice_id": invoice_key,
                        "due_date": due_date.date().isoformat(),
                        "payment_date": payment_date.date().isoformat(),
                        "days_past_due": int(days_late),
                        "payment_id": str(payment["payment_id"]),
                    }
                    rows.append(
                        {
                            **late_base,
                            "entity_id": str(payment["payment_id"]),
                            "vendor_id": str(payment["vendor_id"]),
                            "employee_id": "",
                            "estimated_exposure_inr": 0.0,
                            "detection_reason": (
                                f"Payment is more than {delay_days} days after the due date and the invoice is not disputed. "
                                "Delay alone is not evidence of fraud."
                            ),
                            "supporting_evidence": evidence(payload),
                        }
                    )
                    exception_rows.append(_exception(payment, invoice_key, "LATE_PAYMENT", total, paid_sum))

    exceptions = pd.DataFrame(exception_rows)
    if exceptions.empty:
        exceptions = pd.DataFrame(
            columns=["payment_id", "invoice_id", "vendor_id", "rule_code", "invoice_total_inr", "payment_sum_inr", "payment_amount_inr", "payment_date"]
        )
    return candidates_frame(rows), exceptions.sort_values(["rule_code", "payment_id"]).reset_index(drop=True) if not exceptions.empty else exceptions


def _exception(payment: pd.Series, invoice_id: str, rule_code: str, total: float, paid_sum: float) -> dict:
    return {
        "payment_id": payment["payment_id"],
        "invoice_id": invoice_id,
        "vendor_id": payment["vendor_id"],
        "rule_code": rule_code,
        "invoice_total_inr": round(total, 2),
        "payment_sum_inr": round(paid_sum, 2),
        "payment_amount_inr": round(float(payment["payment_amount_inr"]), 2),
        "payment_date": pd.Timestamp(payment["payment_date"]).date().isoformat(),
    }
