"""Shared shapes for screening outputs."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from src.domain import RULES

CANDIDATE_COLUMNS = [
    "rule_code",
    "rule_name",
    "entity_type",
    "entity_id",
    "vendor_id",
    "employee_id",
    "severity",
    "estimated_exposure_inr",
    "detection_reason",
    "supporting_evidence",
]


def evidence(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def rule_fields(rule_code: str) -> dict[str, str]:
    rule = RULES[rule_code]
    return {
        "rule_code": rule_code,
        "rule_name": rule["name"],
        "entity_type": rule["entity_type"],
        "severity": rule["severity"],
    }


def empty_candidates() -> pd.DataFrame:
    return pd.DataFrame(columns=CANDIDATE_COLUMNS)


def candidates_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return empty_candidates()
    frame = pd.DataFrame(rows)
    for column in CANDIDATE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[CANDIDATE_COLUMNS].sort_values(
        ["rule_code", "entity_type", "entity_id"]
    ).reset_index(drop=True)


def amount_close(left: float, right: float, tolerance: float) -> bool:
    if pd.isna(left) or pd.isna(right):
        return False
    if left <= 0 or right <= 0:
        return False
    baseline = max(abs(float(left)), abs(float(right)))
    return abs(float(left) - float(right)) / baseline <= tolerance


def dated(value: object) -> pd.Timestamp:
    return pd.Timestamp(value)
