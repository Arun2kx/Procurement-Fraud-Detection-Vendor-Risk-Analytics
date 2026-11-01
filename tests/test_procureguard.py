"""Behaviour tests for generation, screening, scoring, and evaluation."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from src.data_generation.generate import generate_datasets
from src.data_ingestion.postgres_loader import split_sql
from src.data_quality.validate import validate_tables
from src.domain import RULES
from src.fraud_detection.detect import detect_patterns
from src.fraud_detection.duplicates import find_exact_duplicate_invoices, find_fuzzy_duplicate_invoices, find_near_time_duplicate_invoices
from src.fraud_detection.splits import find_split_purchase_clusters, split_alerts
from src.reporting.evaluation import confusion
from src.reporting.statistics import benford_analysis
from src.risk_scoring.vendor_risk import classify_risk
from src.utils.config import load_config, validate_risk_weights
from src.utils.identifiers import is_near_sequential, levenshtein, normalize_invoice_number

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def generated():
    config = load_config()
    output = Path(pytest.importorskip("tempfile").mkdtemp(prefix="procureguard_test_"))
    # pytest's tmp_path_factory is preferred; mkdtemp keeps the fixture session-scoped without the factory argument.
    return generate_datasets(config, output_root=output), config


def test_invoice_number_helpers():
    assert normalize_invoice_number("ab-2024/100") == "AB2024100"
    assert levenshtein("AB2024100", "AB2O24100") == 1
    assert is_near_sequential("ABR-2024-10001", "ABR-2024-10020", max_delta=80)
    assert not is_near_sequential("ABR-2024-10001", "ZXQ-2024-88341", max_delta=80)


def test_risk_weights_sum_to_one():
    config = load_config()
    validate_risk_weights(config["risk_weights"])
    assert classify_risk(25, config) == "Low"
    assert classify_risk(25.01, config) == "Medium"
    assert classify_risk(75, config) == "High"
    assert classify_risk(75.01, config) == "Critical"


def test_confusion_formula():
    metrics = confusion({"a", "b"}, {"b", "c"}, {"a", "b", "c", "d"})
    assert metrics["true_positives"] == 1
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 1
    assert metrics["true_negatives"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1_score"] == 0.5


def test_benford_refuses_small_samples():
    config = load_config()
    frame = pd.DataFrame({"amount_inr": [1200, 2400, 3600]})
    result = benford_analysis(frame, "amount_inr", "tiny", config)
    assert result["applicable"] is False
    assert result["chi_square"] is None


def test_sql_splitter_keeps_function_body_together():
    script = "CREATE FUNCTION f() RETURNS int AS $$\nBEGIN\n RETURN 1;\nEND;\n$$ LANGUAGE plpgsql;\nSELECT 1;"
    parts = split_sql(script)
    assert len(parts) == 2
    assert "RETURN 1" in parts[0]


def test_detection_modules_do_not_read_ground_truth():
    for folder in ("fraud_detection", "risk_scoring", "data_quality"):
        for path in (ROOT / "src" / folder).glob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            assert "ground_truth" not in text


def test_generation_shape_and_reproducibility(generated, tmp_path):
    result, config = generated
    counts = result["summary"]["row_counts"]
    assert counts["employees"] == 120
    assert counts["vendors"] == 60
    assert counts["purchase_orders"] == 850
    assert counts["invoices"] == 1500
    assert counts["payments"] == 1400
    assert counts["employee_expenses"] == 900
    assert result["summary"]["synthetic"] is True
    assert not (result["raw_dir"] / "ground_truth_labels.csv").exists()
    labels = result["labels"]
    assert labels["is_suspicious"].any()
    assert labels["is_benign_control"].any()
    assert labels["is_data_quality_defect"].any()
    second = generate_datasets(config, output_root=tmp_path / "second")
    third = generate_datasets(config, output_root=tmp_path / "third")
    for filename in (
        "employees.csv",
        "vendors.csv",
        "purchase_orders.csv",
        "invoices.csv",
        "payments.csv",
        "employee_expenses.csv",
        "approval_records.csv",
    ):
        assert (second["raw_dir"] / filename).read_bytes() == (third["raw_dir"] / filename).read_bytes()


def test_screening_against_planted_labels(generated):
    result, config = generated
    detected_at = datetime(2025, 3, 31, 12, 0, 0)
    detection = detect_patterns(result["tables"], config, detected_at=detected_at)
    alerts = detection["alerts"]
    labels = result["labels"]
    required = {
        "alert_id",
        "entity_type",
        "entity_id",
        "vendor_id",
        "employee_id",
        "rule_code",
        "rule_name",
        "severity",
        "estimated_exposure_inr",
        "detection_reason",
        "supporting_evidence",
        "detection_timestamp",
        "review_status",
    }
    assert required <= set(alerts.columns)
    assert set(alerts["review_status"]) == {"Pending Review"}
    analysis = detection["analysis_tables"]

    def flagged(rule_code: str) -> set[str]:
        return set(alerts.loc[alerts["rule_code"] == rule_code, "entity_id"].astype(str))

    def positives(pattern: str, entity: str) -> set[str]:
        rows = labels[(labels["pattern_code"] == pattern) & (labels["entity_type"] == entity) & (labels["is_suspicious"])]
        return set(rows["entity_id"].astype(str))

    exact = positives("EXACT_DUP_INVOICE", "invoice")
    assert exact <= flagged("EXACT_DUP_INVOICE")
    recurring = set(labels.loc[labels["pattern_code"] == "BENIGN_RECURRING", "entity_id"].astype(str))
    assert recurring.isdisjoint(flagged("EXACT_DUP_INVOICE"))
    assert recurring.isdisjoint(flagged("NEAR_TIME_DUP_INVOICE"))
    near_positive = positives("NEAR_TIME_DUP_INVOICE", "invoice")
    near_flagged = flagged("NEAR_TIME_DUP_INVOICE")
    assert near_flagged < near_positive or len(near_positive - near_flagged) > 0
    assert len(near_positive - near_flagged) == 8
    splits = positives("SPLIT_PURCHASE", "purchase_order")
    assert splits <= flagged("SPLIT_PURCHASE")
    benign_splits = set(labels.loc[labels["pattern_code"] == "BENIGN_VALID_SPLIT", "entity_id"].astype(str))
    assert benign_splits.isdisjoint(flagged("SPLIT_PURCHASE"))
    early = positives("EARLY_PAYMENT", "payment")
    assert early <= flagged("EARLY_PAYMENT")
    assert len(flagged("EARLY_PAYMENT") - early) == 3
    late = positives("LATE_PAYMENT", "payment")
    assert len(flagged("LATE_PAYMENT") - late) == 6
    for entity_id in flagged("EXACT_DUP_INVOICE"):
        assert entity_id in set(analysis["invoices"]["invoice_id"].astype(str))
    assert alerts["estimated_exposure_inr"].ge(0).all()


def test_handmade_duplicate_and_split_rules():
    config = load_config()
    invoices = pd.DataFrame(
        [
            _invoice("I1", "V1", "ABR-2024-10001", "2024-01-01", "ITEM", 1000),
            _invoice("I2", "V1", "ABR-2024-10001", "2024-01-02", "ITEM", 1000),
            _invoice("I3", "V1", "ABR/2024/20001", "2024-02-01", "ITEM", 5000),
            _invoice("I4", "V1", "ABR-2024-20001", "2024-02-02", "ITEM", 5000),
            _invoice("I5", "V1", "ABR-2024-30001", "2024-03-01", "ITEM", 8000),
            _invoice("I6", "V1", "ABR-2024-30002", "2024-03-02", "ITEM", 8000),
            _invoice("I7", "V1", "ABR-2024-40001", "2024-04-01", "ITEM", 9000),
            _invoice("I8", "V1", "QZX-88441", "2024-04-03", "ITEM", 9030),
            _invoice("I9", "V1", "PRF-2024-01", "2024-05-01", "REC-ITEM", 4000, item_code="PRF-REC"),
            _invoice("I10", "V1", "PRF-2024-02", "2024-06-01", "REC-ITEM", 4000, item_code="PRF-REC"),
        ]
    )
    exact = find_exact_duplicate_invoices(invoices)
    assert set(exact["entity_id"]) == {"I1", "I2"}
    fuzzy = find_fuzzy_duplicate_invoices(invoices, config)
    assert {"I3", "I4"} <= set(fuzzy["entity_id"])
    near, _candidates = find_near_time_duplicate_invoices(invoices, config)
    assert {"I7", "I8"} <= set(near["entity_id"])
    assert "I5" not in set(near["entity_id"])
    assert "I9" not in set(near["entity_id"])

    employees = pd.DataFrame(
        [
            {"employee_id": "E1", "approval_limit_inr": 200000, "department": "Facilities"},
            {"employee_id": "E2", "approval_limit_inr": 2000000, "department": "Finance"},
        ]
    )
    orders = pd.DataFrame(
        [
            _po("P1", "V", "2024-01-01", 166000),
            _po("P2", "V", "2024-01-04", 172000),
            _po("P3", "V", "2024-01-08", 178000),
            _po("P4", "V2", "2024-02-01", 162000),
            _po("P5", "V2", "2024-02-04", 168000),
            _po("P6", "V2", "2024-02-07", 174000),
        ]
    )
    approvals = pd.DataFrame(
        [
            _approval("A1", "P1", "E1"),
            _approval("A2", "P2", "E1"),
            _approval("A3", "P3", "E1"),
            _approval("A4", "P4", "E2"),
            _approval("A5", "P5", "E2"),
            _approval("A6", "P6", "E2"),
        ]
    )
    clusters = find_split_purchase_clusters(orders, approvals, employees, config)
    alerts = split_alerts(clusters)
    assert set(alerts["entity_id"]) == {"P1", "P2", "P3"}
    assert set(clusters.loc[clusters["disposition"] == "adequate_approval", "po_id"]) == {"P4", "P5", "P6"}


def test_quality_finds_planted_defects(generated):
    result, config = generated
    summary, failures = validate_tables(result["tables"], config)
    assert not summary["passed"].all()
    assert (failures["check_id"] == "NULL_EMPLOYEE_EMAIL").any()
    assert (failures["check_id"] == "DUPLICATE_BANK_HASH").any()
    assert (failures["check_id"] == "DUPLICATE_PRIMARY_KEY").any()
    assert (failures["check_id"] == "ORPHAN_PO_REFERENCE").any()


def test_rule_catalog_covers_alert_codes():
    assert "EXACT_DUP_INVOICE" in RULES
    assert abs(sum(load_config()["risk_weights"].values()) - 1) < 1e-9


def _invoice(invoice_id, vendor_id, number, invoice_date, description, total, item_code="ITEM"):
    taxable = round(total / 1.18, 2)
    tax = round(total - taxable, 2)
    return {
        "invoice_id": invoice_id,
        "vendor_id": vendor_id,
        "invoice_number": number,
        "invoice_date": date.fromisoformat(invoice_date),
        "item_code": item_code,
        "total_amount_inr": total,
        "invoice_amount_inr": taxable,
        "tax_amount_inr": tax,
        "description": description,
    }


def _po(po_id, vendor_id, po_date, amount):
    return {
        "po_id": po_id,
        "vendor_id": vendor_id,
        "department": "Facilities",
        "category": "Facilities Management",
        "po_date": date.fromisoformat(po_date),
        "po_amount_inr": amount,
        "status": "Approved",
        "requestor_employee_id": "E9",
    }


def _approval(approval_id, po_id, approver):
    return {
        "approval_id": approval_id,
        "entity_type": "purchase_order",
        "entity_id": po_id,
        "approver_employee_id": approver,
        "decision": "Approved",
    }
