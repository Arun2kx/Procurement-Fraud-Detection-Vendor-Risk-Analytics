"""Run the ProcureGuard analytical pipeline.

Screening does not read ground-truth labels. Evaluation is a later step and
writes its metrics only after alerts exist.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.data_generation.generate import generate_datasets
from src.data_ingestion.postgres_loader import apply_analytics_sql, ingest, load_alert_log
from src.data_quality.validate import pass_rate, validate_tables
from src.fraud_detection.detect import detect_patterns
from src.reporting.evaluation import evaluate_rules, render_evaluation_report
from src.reporting.exports import export_powerbi
from src.reporting.figures import save_figures
from src.reporting.narratives import write_audit_findings, write_quality_report, write_statistics_note
from src.reporting.reconciliation import concentration, reconcile
from src.reporting.statistics import expense_benford, invoice_benford, statistical_outliers
from src.risk_scoring.vendor_risk import attach_vendor_scores, score_vendors
from src.utils.config import load_config, project_path
from src.utils.frames import read_operational_tables, write_table


def analyze(config: dict, detected_at: datetime | None = None) -> dict:
    raw_dir = project_path(config, "raw_dir")
    processed = project_path(config, "processed_dir")
    evaluation_dir = project_path(config, "evaluation_dir")
    reports = project_path(config, "reports_dir")
    figures = project_path(config, "figures_dir")
    screenshots = project_path(config, "screenshots_dir")
    processed.mkdir(parents=True, exist_ok=True)

    tables = read_operational_tables(raw_dir)
    labels = _read_labels(evaluation_dir / "ground_truth_labels.csv")
    quality_summary, quality_failures = validate_tables(tables, config)
    detection = detect_patterns(tables, config, detected_at=detected_at)
    analysis_tables = detection.pop("analysis_tables")
    invoice_digits = invoice_benford(analysis_tables["invoices"], config)
    expense_digits = expense_benford(analysis_tables["employee_expenses"], config)
    outliers = statistical_outliers(analysis_tables["invoices"], analysis_tables["vendors"], config)
    reconciliation = reconcile(analysis_tables, config)
    vendor_spend, hhi, department_month = concentration(analysis_tables)
    scores = score_vendors(
        analysis_tables,
        detection["alerts"],
        detection["split_purchase_clusters"],
        detection["price_volatility"],
        config,
    )
    alerts = attach_vendor_scores(detection["alerts"], scores)
    metrics = evaluate_rules(alerts, labels, analysis_tables)

    write_table(quality_summary, processed / "data_quality_checks.csv")
    write_table(quality_failures, processed / "data_quality_failures.csv")
    write_table(alerts, processed / "audit_alerts.csv")
    write_table(detection["excluded_duplicate_keys"], processed / "excluded_duplicate_keys.csv")
    write_table(detection["duplicate_invoice_candidates"], processed / "duplicate_invoice_candidates.csv")
    write_table(detection["split_purchase_clusters"], processed / "split_purchase_clusters.csv")
    write_table(detection["payment_exceptions"], processed / "payment_exceptions.csv")
    write_table(detection["price_volatility"], processed / "price_volatility.csv")
    write_table(scores, processed / "vendor_risk_scores.csv")
    write_table(reconciliation, processed / "reconciliation.csv")
    write_table(vendor_spend, processed / "vendor_concentration.csv")
    write_table(hhi, processed / "category_hhi.csv")
    write_table(department_month, processed / "department_monthly_spend.csv")
    write_table(outliers, processed / "statistical_outliers.csv")
    write_table(
        pd.concat([invoice_digits["distribution"], expense_digits["distribution"]], ignore_index=True),
        processed / "benford_digits.csv",
        float_format="%.6f",
    )
    write_table(metrics, evaluation_dir / "rule_metrics.csv", float_format="%.6f")
    write_table(_missingness(tables), processed / "missingness.csv")
    factor_columns = [column for column in scores.columns if column.startswith("score_")]
    write_table(scores[factor_columns].corr().reset_index().rename(columns={"index": "factor"}), processed / "risk_factor_correlation.csv")

    write_quality_report(quality_summary, quality_failures, reports / "data_quality_report.md")
    write_audit_findings(alerts, reports / "sample_audit_findings.md")
    write_statistics_note(invoice_digits, expense_digits, len(outliers), reports / "statistical_screening.md")
    render_evaluation_report(metrics, reports / "evaluation_report.md")
    export_powerbi(
        analysis_tables,
        alerts,
        scores,
        reconciliation,
        pd.concat([invoice_digits["distribution"], expense_digits["distribution"]], ignore_index=True),
        metrics,
        quality_summary,
        config,
        project_path(config, "powerbi_dir"),
    )
    save_figures(analysis_tables, alerts, scores, invoice_digits["distribution"], vendor_spend, figures)
    screenshots.mkdir(parents=True, exist_ok=True)
    for figure in figures.glob("*.png"):
        shutil.copy2(figure, screenshots / figure.name)

    high_critical = int(scores["risk_category"].isin(["High", "Critical"]).sum())
    exposure = float(pd.to_numeric(alerts["estimated_exposure_inr"], errors="coerce").fillna(0).sum())
    summary = {
        "generated_at": datetime.now().replace(microsecond=0).isoformat(sep=" "),
        "currency": "INR",
        "synthetic": True,
        "alerts": int(len(alerts)),
        "potential_exposure_inr": round(exposure, 2),
        "high_or_critical_vendors": high_critical,
        "vendors_scored": int(len(scores)),
        "data_quality_pass_rate": round(pass_rate(quality_summary), 4),
        "data_quality_failed_checks": int((~quality_summary["passed"]).sum()),
        "benford_invoice_applicable": invoice_digits["applicable"],
        "benford_invoice_sample_size": invoice_digits["sample_size"],
        "benford_invoice_mad": invoice_digits["mad"],
        "benford_invoice_p_value": invoice_digits["p_value"],
        "benford_invoice_band": invoice_digits["conformity_band"],
        "benford_expense_mad": expense_digits["mad"],
        "benford_expense_p_value": expense_digits["p_value"],
        "benford_expense_band": expense_digits["conformity_band"],
        "statistical_outlier_rows": int(len(outliers)),
        "isolation_forest_flags": int(scores["isolation_forest_flag"].sum()),
        "rule_metrics": metrics[
            ["rule_code", "positives", "predicted", "true_positives", "false_positives", "false_negatives", "precision", "recall", "f1_score"]
        ].to_dict("records"),
    }
    (reports / "run_summary.json").write_text(json.dumps(summary, indent=2, default=_json_default), encoding="utf-8")
    return summary


def _json_default(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(type(value))


def _read_labels(path: Path) -> pd.DataFrame:
    labels = pd.read_csv(path)
    for column in ("is_suspicious", "is_benign_control", "is_data_quality_defect"):
        labels[column] = labels[column].astype(str).str.lower().isin(["true", "1"])
    return labels


def _missingness(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, frame in tables.items():
        for column in frame.columns:
            missing = int(frame[column].isna().sum())
            rows.append(
                {
                    "table_name": name,
                    "column_name": column,
                    "missing_rows": missing,
                    "missing_rate": round(missing / len(frame), 6) if len(frame) else 0,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ProcureGuard synthetic analytics pipeline.")
    parser.add_argument("command", nargs="?", default="all", choices=["all", "generate", "analyze", "ingest", "sql"])
    args = parser.parse_args()
    config = load_config()
    root = Path(config["_project_root"])
    if args.command in {"all", "generate"}:
        generate_datasets(config)
        print("Generated synthetic datasets.")
    if args.command in {"all", "analyze"}:
        summary = analyze(config)
        print(json.dumps({key: summary[key] for key in ("alerts", "potential_exposure_inr", "high_or_critical_vendors", "data_quality_pass_rate")}, indent=2))
    if args.command == "ingest":
        counts = ingest(
            config,
            project_path(config, "raw_dir"),
            root / "database" / "01_schema.sql",
            project_path(config, "processed_dir") / "ingestion_rejections.csv",
        )
        alerts = pd.read_csv(project_path(config, "processed_dir") / "audit_alerts.csv")
        print(counts.to_string(index=False))
        if not alerts.empty and "alert_id" in alerts.columns:
            print(f"Loaded alerts: {load_alert_log(config, alerts)}")
    if args.command == "sql":
        apply_analytics_sql(config, root / "database")
        print("Applied SQL analytics views.")


if __name__ == "__main__":
    main()
