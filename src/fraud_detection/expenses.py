"""Employee expense screening rules."""

from __future__ import annotations

import pandas as pd

from src.fraud_detection.common import candidates_frame, evidence, rule_fields
from src.utils.grouping import UnionFind


def _prepare(expenses: pd.DataFrame) -> pd.DataFrame:
    frame = expenses.copy()
    frame["expense_date"] = pd.to_datetime(frame["expense_date"])
    frame["submitted_at"] = pd.to_datetime(frame["submitted_at"])
    frame["amount_inr"] = pd.to_numeric(frame["amount_inr"], errors="coerce")
    return frame


def find_duplicate_expenses(expenses: pd.DataFrame) -> pd.DataFrame:
    """Flag claims with the same employee, category, and amount within one day."""
    work = _prepare(expenses)
    work = work[work["amount_inr"] > 0].copy()
    work["amount_key"] = work["amount_inr"].round(2)
    union = UnionFind()
    for _, group in work.groupby(["employee_id", "category", "amount_key"], sort=True):
        records = group.sort_values(["expense_date", "expense_id"]).to_dict("records")
        for record in records:
            union.add(str(record["expense_id"]))
        for left_index, left in enumerate(records):
            for right in records[left_index + 1 :]:
                if abs((right["expense_date"] - left["expense_date"]).days) <= 1:
                    union.union(str(left["expense_id"]), str(right["expense_id"]))
    base = rule_fields("DUPLICATE_EXPENSE")
    indexed = work.set_index("expense_id", drop=True)
    rows: list[dict] = []
    for members in union.groups():
        if len(members) < 2:
            continue
        member_rows = indexed.loc[members].reset_index().sort_values(["expense_date", "expense_id"])
        anchor = str(member_rows.iloc[0]["expense_id"])
        payload = {
            "expense_ids": [str(value) for value in member_rows["expense_id"]],
            "employee_id": str(member_rows.iloc[0]["employee_id"]),
            "category": str(member_rows.iloc[0]["category"]),
            "amount_inr": round(float(member_rows.iloc[0]["amount_inr"]), 2),
        }
        for _, row in member_rows.iterrows():
            rows.append(
                {
                    **base,
                    "entity_id": str(row["expense_id"]),
                    "vendor_id": "",
                    "employee_id": str(row["employee_id"]),
                    "estimated_exposure_inr": 0.0 if str(row["expense_id"]) == anchor else round(float(row["amount_inr"]), 2),
                    "detection_reason": "Same employee, category, and amount were claimed within one day.",
                    "supporting_evidence": evidence(payload),
                }
            )
    return candidates_frame(rows)


def find_threshold_gaming_expenses(expenses: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Flag repeated claims sitting just below a category receipt threshold."""
    thresholds = {key: float(value) for key, value in config["expense_category_thresholds_inr"].items()}
    ratio = float(config["thresholds"]["near_threshold_ratio"])
    window_days = int(config["thresholds"]["expense_repeat_window_days"])
    minimum = int(config["thresholds"]["expense_repeat_min_count"])
    work = _prepare(expenses)
    work = work[work["amount_inr"] > 0].copy()
    flagged: list[dict] = []
    for (employee_id, category), group in work.groupby(["employee_id", "category"], sort=True):
        limit = thresholds.get(str(category))
        if limit is None:
            continue
        low = limit * ratio
        band = group[(group["amount_inr"] >= low) & (group["amount_inr"] < limit)]
        records = band.sort_values(["expense_date", "expense_id"]).to_dict("records")
        seen: set[str] = set()
        left = 0
        for right, record in enumerate(records):
            while (record["expense_date"] - records[left]["expense_date"]).days > window_days:
                left += 1
            if right - left + 1 >= minimum:
                for member in records[left : right + 1]:
                    if str(member["expense_id"]) not in seen:
                        seen.add(str(member["expense_id"]))
                        flagged.append(member | {"threshold_inr": limit})
    base = rule_fields("THRESHOLD_GAMING_EXPENSE")
    rows: list[dict] = []
    buckets: dict[tuple[str, str], list[dict]] = {}
    for record in flagged:
        buckets.setdefault((str(record["employee_id"]), str(record["category"])), []).append(record)
    for (employee_id, category), members in sorted(buckets.items()):
        ordered = sorted(members, key=lambda item: (item["expense_date"], item["expense_id"]))
        anchor = str(ordered[0]["expense_id"])
        total = round(sum(float(item["amount_inr"]) for item in ordered), 2)
        payload = {
            "employee_id": employee_id,
            "category": category,
            "expense_ids": [str(item["expense_id"]) for item in ordered],
            "amounts_inr": [round(float(item["amount_inr"]), 2) for item in ordered],
            "category_threshold_inr": ordered[0]["threshold_inr"],
        }
        for item in ordered:
            rows.append(
                {
                    **base,
                    "entity_id": str(item["expense_id"]),
                    "vendor_id": "",
                    "employee_id": employee_id,
                    "estimated_exposure_inr": total if str(item["expense_id"]) == anchor else 0.0,
                    "detection_reason": (
                        "Repeated claims fall just below the category threshold inside the review window."
                    ),
                    "supporting_evidence": evidence(payload),
                }
            )
    return candidates_frame(rows)


def find_offhours_expenses(expenses: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Flag weekend claims submitted late at night without a receipt.

    A weekend date or a missing receipt on its own does not create an alert.
    """
    minimum = float(config["thresholds"]["offhours_min_amount_inr"])
    work = _prepare(expenses)
    submitted = work["submitted_at"]
    weekend = submitted.dt.dayofweek >= 5
    late_night = (submitted.dt.hour >= 22) | (submitted.dt.hour < 6)
    mask = weekend & late_night & (~work["receipt_attached"].astype(bool)) & (work["amount_inr"] >= minimum)
    base = rule_fields("OFFHOURS_EXPENSE")
    rows: list[dict] = []
    for _, row in work.loc[mask].sort_values("expense_id").iterrows():
        payload = {
            "expense_id": str(row["expense_id"]),
            "employee_id": str(row["employee_id"]),
            "submitted_at": pd.Timestamp(row["submitted_at"]).isoformat(),
            "amount_inr": round(float(row["amount_inr"]), 2),
            "category": str(row["category"]),
            "receipt_attached": False,
        }
        rows.append(
            {
                **base,
                "entity_id": str(row["expense_id"]),
                "vendor_id": "",
                "employee_id": str(row["employee_id"]),
                "estimated_exposure_inr": round(float(row["amount_inr"]), 2),
                "detection_reason": (
                    "The claim was submitted over a weekend outside working hours and has no receipt. "
                    "This is a review indicator, not a confirmed irregularity."
                ),
                "supporting_evidence": evidence(payload),
            }
        )
    return candidates_frame(rows)
