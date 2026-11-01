"""Invoice duplicate screening.

Exact matches use the raw invoice number, ignoring only letter case.
Fuzzy matches use a normalised number or a one-character edit that is not a
short step along the same numeric series. Near-time matches require a distant
invoice number so ordinary billing series are left for manual candidate review.
"""

from __future__ import annotations

import pandas as pd

from src.fraud_detection.common import amount_close, candidates_frame, dated, evidence, rule_fields
from src.utils.grouping import UnionFind
from src.utils.identifiers import (
    casefold_invoice_number,
    is_near_sequential,
    levenshtein,
    normalize_invoice_number,
)


def _prepare(invoices: pd.DataFrame) -> pd.DataFrame:
    work = invoices.copy()
    work["invoice_date"] = pd.to_datetime(work["invoice_date"])
    work["casefold_number"] = work["invoice_number"].map(casefold_invoice_number)
    work["norm_number"] = work["invoice_number"].map(normalize_invoice_number)
    work["total_amount_inr"] = pd.to_numeric(work["total_amount_inr"], errors="coerce")
    return work


def _emit_groups(
    work: pd.DataFrame,
    groups: list[list[str]],
    rule_code: str,
    reason: str,
    extra_evidence: dict | None = None,
) -> list[dict]:
    rows: list[dict] = []
    indexed = work.set_index("invoice_id", drop=True)
    base = rule_fields(rule_code)
    for members in groups:
        if len(members) < 2:
            continue
        member_rows = indexed.loc[members]
        if isinstance(member_rows, pd.Series):
            member_rows = member_rows.to_frame().T
        ordered = member_rows.reset_index().sort_values(["invoice_date", "invoice_id"])
        anchor_id = str(ordered.iloc[0]["invoice_id"])
        payload = {
            "anchor_invoice_id": anchor_id,
            "invoice_ids": [str(value) for value in ordered["invoice_id"]],
            "invoice_numbers": [str(value) for value in ordered["invoice_number"]],
            "totals_inr": [None if pd.isna(value) else round(float(value), 2) for value in ordered["total_amount_inr"]],
            "vendor_id": str(ordered.iloc[0]["vendor_id"]),
        }
        if extra_evidence:
            payload.update(extra_evidence)
        for _, row in ordered.iterrows():
            is_anchor = str(row["invoice_id"]) == anchor_id
            total = row["total_amount_inr"]
            exposure = 0.0 if is_anchor or pd.isna(total) else round(float(total), 2)
            rows.append(
                {
                    **base,
                    "entity_id": str(row["invoice_id"]),
                    "vendor_id": str(row["vendor_id"]),
                    "employee_id": "",
                    "estimated_exposure_inr": exposure,
                    "detection_reason": reason,
                    "supporting_evidence": evidence(payload),
                }
            )
    return rows


def find_exact_duplicate_invoices(invoices: pd.DataFrame) -> pd.DataFrame:
    """Flag invoices that reuse the same vendor and invoice number."""
    work = _prepare(invoices)
    work = work[work["casefold_number"] != ""]
    groups: list[list[str]] = []
    for (_, _), group in work.groupby(["vendor_id", "casefold_number"], sort=True):
        if len(group) > 1:
            groups.append(sorted(group["invoice_id"].astype(str)))
    rows = _emit_groups(
        work,
        groups,
        "EXACT_DUP_INVOICE",
        "More than one invoice uses the same vendor and invoice number.",
    )
    return candidates_frame(rows)


def find_fuzzy_duplicate_invoices(invoices: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Flag punctuation variants and single-character invoice-number edits."""
    work = _prepare(invoices)
    window_days = int(config["thresholds"]["fuzzy_window_days"])
    tolerance = float(config["thresholds"]["fuzzy_amount_tolerance"])
    max_distance = int(config["thresholds"]["fuzzy_max_distance"])
    max_delta = int(config["thresholds"]["sequential_invoice_max_delta"])
    union = UnionFind()
    pair_notes: list[str] = []

    for _, group in work.groupby("vendor_id", sort=True):
        records = group.to_dict("records")
        by_norm: dict[str, list[dict]] = {}
        for record in records:
            if record["norm_number"]:
                by_norm.setdefault(record["norm_number"], []).append(record)
        for members in by_norm.values():
            casefolds = {record["casefold_number"] for record in members}
            if len(casefolds) < 2:
                continue
            for left_index, left in enumerate(members):
                for right in members[left_index + 1 :]:
                    if left["casefold_number"] == right["casefold_number"]:
                        continue
                    if not amount_close(left["total_amount_inr"], right["total_amount_inr"], tolerance):
                        continue
                    union.union(str(left["invoice_id"]), str(right["invoice_id"]))
                    pair_notes.append("normalised_invoice_number")

        for left_index, left in enumerate(records):
            for right in records[left_index + 1 :]:
                if not left["norm_number"] or not right["norm_number"]:
                    continue
                if left["norm_number"] == right["norm_number"]:
                    continue
                if is_near_sequential(left["invoice_number"], right["invoice_number"], max_delta):
                    continue
                if abs((dated(left["invoice_date"]) - dated(right["invoice_date"])).days) > window_days:
                    continue
                if levenshtein(left["norm_number"], right["norm_number"]) > max_distance:
                    continue
                if not amount_close(left["total_amount_inr"], right["total_amount_inr"], tolerance):
                    continue
                union.union(str(left["invoice_id"]), str(right["invoice_id"]))
                pair_notes.append("edit_distance")

    groups = [members for members in union.groups() if len(members) > 1]
    rows = _emit_groups(
        work,
        groups,
        "FUZZY_DUP_INVOICE",
        "Invoice numbers match after normalisation or differ by a single character, excluding short sequential gaps.",
        {"pair_notes": sorted(set(pair_notes))},
    )
    return candidates_frame(rows)


def find_near_time_duplicate_invoices(invoices: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Flag close-dated, close-amount invoices whose numbers are not a short series.

    Pairs that otherwise match but have a short invoice-number gap are returned
    in the candidate extract with disposition ``excluded_sequential``. Recurring
    contract items (item codes ending in ``-REC``) are excluded.
    """
    work = _prepare(invoices)
    window_days = int(config["thresholds"]["near_duplicate_window_days"])
    tolerance = float(config["thresholds"]["near_duplicate_amount_tolerance"])
    max_delta = int(config["thresholds"]["sequential_invoice_max_delta"])
    fuzzy_distance = int(config["thresholds"]["fuzzy_max_distance"])
    union = UnionFind()
    candidate_rows: list[dict] = []

    for _, group in work.groupby("vendor_id", sort=True):
        records = [record for record in group.to_dict("records") if str(record.get("item_code", "")).endswith("-REC") is False]
        records = [record for record in records if pd.notna(record["total_amount_inr"]) and record["total_amount_inr"] > 0]
        for left_index, left in enumerate(records):
            for right in records[left_index + 1 :]:
                day_gap = abs((dated(left["invoice_date"]) - dated(right["invoice_date"])).days)
                if day_gap > window_days:
                    continue
                if left.get("item_code") != right.get("item_code"):
                    continue
                if left["casefold_number"] == right["casefold_number"]:
                    continue
                if not amount_close(left["total_amount_inr"], right["total_amount_inr"], tolerance):
                    continue
                sequential = is_near_sequential(left["invoice_number"], right["invoice_number"], max_delta)
                normalised_same = left["norm_number"] == right["norm_number"] and left["norm_number"] != ""
                close_edit = (
                    left["norm_number"]
                    and right["norm_number"]
                    and levenshtein(left["norm_number"], right["norm_number"]) <= fuzzy_distance
                )
                if sequential:
                    disposition = "excluded_sequential"
                elif normalised_same or close_edit:
                    disposition = "classified_as_fuzzy"
                else:
                    disposition = "alert"
                    union.union(str(left["invoice_id"]), str(right["invoice_id"]))
                candidate_rows.append(
                    {
                        "vendor_id": left["vendor_id"],
                        "left_invoice_id": left["invoice_id"],
                        "right_invoice_id": right["invoice_id"],
                        "left_invoice_number": left["invoice_number"],
                        "right_invoice_number": right["invoice_number"],
                        "day_gap": int(day_gap),
                        "left_total_inr": round(float(left["total_amount_inr"]), 2),
                        "right_total_inr": round(float(right["total_amount_inr"]), 2),
                        "disposition": disposition,
                    }
                )

    groups = [members for members in union.groups() if len(members) > 1]
    alerts = candidates_frame(
        _emit_groups(
            work,
            groups,
            "NEAR_TIME_DUP_INVOICE",
            "Same vendor and item, amounts within tolerance, dates inside the short window, and invoice numbers outside a normal series.",
        )
    )
    candidates = pd.DataFrame(candidate_rows)
    if candidates.empty:
        candidates = pd.DataFrame(
            columns=[
                "vendor_id",
                "left_invoice_id",
                "right_invoice_id",
                "left_invoice_number",
                "right_invoice_number",
                "day_gap",
                "left_total_inr",
                "right_total_inr",
                "disposition",
            ]
        )
    else:
        candidates = candidates.sort_values(["vendor_id", "left_invoice_id", "right_invoice_id"]).reset_index(drop=True)
    return alerts, candidates
