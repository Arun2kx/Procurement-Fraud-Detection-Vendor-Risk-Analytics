"""Markdown reports built only from pipeline outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_quality.validate import pass_rate


def write_quality_report(summary: pd.DataFrame, failures: pd.DataFrame, path: Path) -> None:
    rate = pass_rate(summary)
    failed = summary[~summary["passed"]]
    lines = [
        "# Data quality report",
        "",
        "This report describes the synthetic raw files. Failed checks are retained in those files.",
        "Rows rejected later by a PostgreSQL constraint are listed in the ingestion rejection log and are not silently deleted here.",
        "",
        f"- Checks executed: {len(summary)}",
        f"- Checks passed: {int(summary['passed'].sum())}",
        f"- Check pass rate: {rate:.2%}",
        f"- Failed-record rows: {len(failures)}",
        "",
        "## Failed checks",
        "",
    ]
    if failed.empty:
        lines.append("No listed check failed.")
    else:
        for _, row in failed.sort_values("failure_count", ascending=False).iterrows():
            lines.append(f"- {row['check_id']} on {row['table_name']}: {int(row['failure_count'])} rows")
    lines.extend(["", "A failed check is a data defect or a referential break. It is not, by itself, a fraud finding.", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_audit_findings(alerts: pd.DataFrame, path: Path, limit: int = 8) -> None:
    lines = [
        "# Sample audit findings",
        "",
        "Each item below is a synthetic screening alert. Review status starts at Pending Review.",
        "None of these items is a confirmed fraud, a real loss, or a real vendor.",
        "",
    ]
    if alerts.empty:
        lines.append("No alerts were produced.")
        path.write_text("\n".join(lines), encoding="utf-8")
        return
    severity = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    ranked = alerts.copy()
    ranked["severity_rank"] = ranked["severity"].map(severity)
    ranked = ranked.sort_values(["severity_rank", "estimated_exposure_inr"], ascending=[True, False]).head(limit)
    for _, row in ranked.iterrows():
        lines.extend(
            [
                f"## {row['alert_id']} — {row['rule_name']}",
                "",
                f"- Rule: {row['rule_code']}",
                f"- Severity: {row['severity']}",
                f"- Entity: {row['entity_type']} {row['entity_id']}",
                f"- Vendor: {row['vendor_id'] or 'n/a'}",
                f"- Employee: {row['employee_id'] or 'n/a'}",
                f"- Potential exposure (INR): {float(row['estimated_exposure_inr']):,.2f}",
                f"- Review status: {row['review_status']}",
                f"- Reason: {row['detection_reason']}",
                f"- Evidence: {row['supporting_evidence']}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_statistics_note(invoice_benford: dict, expense_benford: dict, outlier_count: int, path: Path) -> None:
    lines = [
        "# Statistical screening note",
        "",
        "Benford and outlier screens are not fraud alerts.",
        "",
        "## Non-recurring invoices",
        "",
        f"- Applicable: {invoice_benford['applicable']}",
        f"- Sample size: {invoice_benford['sample_size']}",
        f"- Chi-square: {invoice_benford['chi_square']}",
        f"- p-value: {invoice_benford['p_value']}",
        f"- Mean absolute deviation: {invoice_benford['mad']}",
        f"- Conformity band: {invoice_benford['conformity_band']}",
        f"- Limitation: {invoice_benford['limitation']}",
        "",
        "## Employee expenses",
        "",
        f"- Applicable: {expense_benford['applicable']}",
        f"- Sample size: {expense_benford['sample_size']}",
        f"- Chi-square: {expense_benford['chi_square']}",
        f"- p-value: {expense_benford['p_value']}",
        f"- Mean absolute deviation: {expense_benford['mad']}",
        f"- Conformity band: {expense_benford['conformity_band']}",
        f"- Limitation: {expense_benford['limitation']}",
        "",
        f"Category-adjusted statistical outlier rows written: {outlier_count}.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
