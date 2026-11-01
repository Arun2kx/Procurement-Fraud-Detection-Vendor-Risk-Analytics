"""Star-schema extracts for Power BI Import mode."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.utils.frames import write_table


def build_date_dimension(start: str, end: str) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    frame = pd.DataFrame({"date": days})
    frame["year"] = frame["date"].dt.year
    frame["quarter"] = frame["date"].dt.quarter
    frame["month"] = frame["date"].dt.month
    frame["month_name"] = frame["date"].dt.strftime("%b")
    frame["year_month"] = frame["date"].dt.strftime("%Y-%m")
    frame["day_name"] = frame["date"].dt.day_name()
    frame["is_weekend"] = frame["date"].dt.dayofweek >= 5
    fiscal_year = frame["date"].dt.year.where(frame["date"].dt.month >= 4, frame["date"].dt.year - 1)
    frame["fiscal_year_label"] = fiscal_year.map(lambda year: f"FY{int(year)}-{str(int(year) + 1)[-2:]}")
    frame["fiscal_quarter"] = (((frame["date"].dt.month + 8) % 12) // 3) + 1
    frame["date"] = frame["date"].dt.date
    return frame


def export_powerbi(
    tables: dict[str, pd.DataFrame],
    alerts: pd.DataFrame,
    scores: pd.DataFrame,
    reconciliation: pd.DataFrame,
    benford: pd.DataFrame,
    metrics: pd.DataFrame,
    quality_summary: pd.DataFrame,
    config: dict,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_table(build_date_dimension(config["date_range"]["start"], config["date_range"]["end"]), output_dir / "dim_date.csv")
    write_table(tables["vendors"], output_dir / "dim_vendor.csv")
    write_table(tables["employees"], output_dir / "dim_employee.csv")
    write_table(tables["invoices"], output_dir / "fact_invoice.csv")
    write_table(tables["payments"], output_dir / "fact_payment.csv")
    write_table(tables["purchase_orders"], output_dir / "fact_purchase_order.csv")
    write_table(tables["employee_expenses"], output_dir / "fact_expense.csv")
    write_table(tables["approval_records"], output_dir / "fact_approval.csv")
    write_table(alerts, output_dir / "fact_alert.csv")
    write_table(scores, output_dir / "fact_vendor_risk.csv")
    write_table(reconciliation, output_dir / "fact_reconciliation.csv")
    write_table(benford, output_dir / "fact_benford.csv", float_format="%.6f")
    write_table(metrics, output_dir / "fact_rule_performance.csv", float_format="%.6f")
    write_table(quality_summary, output_dir / "fact_data_quality.csv")
