"""Run every screening rule on operational tables.

This module does not read ground-truth labels.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.domain import SEVERITY_RANK
from src.fraud_detection.approvals import find_po_approval_issues, find_self_approvals
from src.fraud_detection.common import CANDIDATE_COLUMNS
from src.fraud_detection.duplicates import (
    find_exact_duplicate_invoices,
    find_fuzzy_duplicate_invoices,
    find_near_time_duplicate_invoices,
)
from src.fraud_detection.expenses import (
    find_duplicate_expenses,
    find_offhours_expenses,
    find_threshold_gaming_expenses,
)
from src.fraud_detection.payments import find_payment_exceptions
from src.fraud_detection.splits import find_split_purchase_clusters, find_threshold_gaming, split_alerts
from src.fraud_detection.vendors import find_high_dispute_rates, find_price_volatility
from src.utils.frames import PRIMARY_KEYS, split_duplicate_keys


def _analysis_tables(tables: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Separate repeated primary keys from the frames used for screening."""
    prepared = {}
    excluded_rows = []
    for name, frame in tables.items():
        key = PRIMARY_KEYS[name]
        kept, excluded = split_duplicate_keys(frame, key)
        prepared[name] = kept
        if not excluded.empty:
            excluded = excluded.copy()
            excluded.insert(0, "table_name", name)
            excluded.insert(1, "exclusion_reason", "duplicate_primary_key")
            excluded_rows.append(excluded)
    if excluded_rows:
        excluded_frame = pd.concat(excluded_rows, ignore_index=True)
    else:
        excluded_frame = pd.DataFrame(columns=["table_name", "exclusion_reason"])
    return prepared, excluded_frame


def build_alert_log(candidates: pd.DataFrame, detected_at: datetime | None = None) -> pd.DataFrame:
    """Assign stable alert ids. Exposure is stored on the anchor row of a group."""
    if candidates.empty:
        return pd.DataFrame(
            columns=[
                "alert_id",
                "entity_type",
                "entity_id",
                "vendor_id",
                "employee_id",
                "rule_code",
                "rule_name",
                "severity",
                "risk_score",
                "estimated_exposure_inr",
                "detection_reason",
                "supporting_evidence",
                "detection_timestamp",
                "review_status",
            ]
        )
    frame = candidates.copy()
    frame["severity_rank"] = frame["severity"].map(SEVERITY_RANK)
    frame = frame.sort_values(["severity_rank", "rule_code", "entity_type", "entity_id"]).reset_index(drop=True)
    timestamp = (detected_at or datetime.now()).replace(microsecond=0).isoformat(sep=" ")
    frame.insert(0, "alert_id", [f"ALT{index:06d}" for index in range(1, len(frame) + 1)])
    frame["risk_score"] = pd.NA
    frame["detection_timestamp"] = timestamp
    frame["review_status"] = "Pending Review"
    return frame[
        [
            "alert_id",
            "entity_type",
            "entity_id",
            "vendor_id",
            "employee_id",
            "rule_code",
            "rule_name",
            "severity",
            "risk_score",
            "estimated_exposure_inr",
            "detection_reason",
            "supporting_evidence",
            "detection_timestamp",
            "review_status",
        ]
    ]


def detect_patterns(tables: dict[str, pd.DataFrame], config: dict, detected_at: datetime | None = None) -> dict[str, pd.DataFrame]:
    """Return alerts and the supporting extracts for each screening rule."""
    prepared, excluded = _analysis_tables(tables)
    exact = find_exact_duplicate_invoices(prepared["invoices"])
    fuzzy = find_fuzzy_duplicate_invoices(prepared["invoices"], config)
    near, near_candidates = find_near_time_duplicate_invoices(prepared["invoices"], config)
    clusters = find_split_purchase_clusters(
        prepared["purchase_orders"],
        prepared["approval_records"],
        prepared["employees"],
        config,
    )
    splits = split_alerts(clusters)
    gaming = find_threshold_gaming(prepared["purchase_orders"], config)
    payment_alerts, payment_exceptions = find_payment_exceptions(prepared["payments"], prepared["invoices"], config)
    duplicate_expenses = find_duplicate_expenses(prepared["employee_expenses"])
    expense_gaming = find_threshold_gaming_expenses(prepared["employee_expenses"], config)
    offhours = find_offhours_expenses(prepared["employee_expenses"], config)
    self_approvals = find_self_approvals(
        prepared["approval_records"],
        prepared["purchase_orders"],
        prepared["employee_expenses"],
    )
    approval_issues = find_po_approval_issues(
        prepared["purchase_orders"],
        prepared["approval_records"],
        prepared["employees"],
        config,
    )
    volatility_alerts, volatility_metrics = find_price_volatility(prepared["invoices"], config)
    disputes = find_high_dispute_rates(prepared["invoices"], config)
    candidate_frames = [
        exact,
        fuzzy,
        near,
        splits,
        gaming,
        payment_alerts,
        duplicate_expenses,
        expense_gaming,
        offhours,
        self_approvals,
        approval_issues,
        volatility_alerts,
        disputes,
    ]
    candidates = pd.concat([frame for frame in candidate_frames if not frame.empty], ignore_index=True)
    if candidates.empty:
        candidates = pd.DataFrame(columns=CANDIDATE_COLUMNS)
    alerts = build_alert_log(candidates, detected_at=detected_at)
    return {
        "alerts": alerts,
        "excluded_duplicate_keys": excluded,
        "duplicate_invoice_candidates": near_candidates,
        "exact_duplicate_alerts": exact,
        "fuzzy_duplicate_alerts": fuzzy,
        "split_purchase_clusters": clusters,
        "payment_exceptions": payment_exceptions,
        "price_volatility": volatility_metrics,
        "analysis_tables": prepared,
    }
