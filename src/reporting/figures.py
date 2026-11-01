"""Matplotlib and seaborn charts for the analytical appendix.

These files are pipeline previews. They are not Power BI screenshots.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

NAVY = "#0B1F3A"
GOLD = "#C4A35A"
TEAL = "#1F6F8B"
LIGHT = "#F4F7FB"


def _style() -> None:
    sns.set_theme(style="whitegrid")
    plt.rcParams["axes.edgecolor"] = NAVY
    plt.rcParams["axes.labelcolor"] = NAVY
    plt.rcParams["xtick.color"] = NAVY
    plt.rcParams["ytick.color"] = NAVY
    plt.rcParams["text.color"] = NAVY
    plt.rcParams["figure.facecolor"] = "white"


def save_figures(
    tables: dict[str, pd.DataFrame],
    alerts: pd.DataFrame,
    scores: pd.DataFrame,
    benford_distribution: pd.DataFrame,
    vendor_spend: pd.DataFrame,
    output_dir: Path,
) -> list[Path]:
    _style()
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    written.append(_monthly_spend(tables["invoices"], output_dir / "01_monthly_spend.png"))
    written.append(_department_spend(tables, output_dir / "02_department_spend.png"))
    written.append(_risk_distribution(scores, output_dir / "03_vendor_risk_distribution.png"))
    written.append(_alerts_by_rule(alerts, output_dir / "04_alerts_by_rule.png"))
    written.append(_benford(benford_distribution, output_dir / "05_benford_invoices.png"))
    written.append(_pareto(vendor_spend, output_dir / "06_vendor_pareto.png"))
    written.append(_amount_hist(tables["invoices"], output_dir / "07_invoice_amount_distribution.png"))
    return [path for path in written if path is not None]


def _monthly_spend(invoices: pd.DataFrame, path: Path) -> Path:
    work = invoices.drop_duplicates("invoice_id").copy()
    work["total_amount_inr"] = pd.to_numeric(work["total_amount_inr"], errors="coerce").fillna(0).clip(lower=0)
    work["invoice_date"] = pd.to_datetime(work["invoice_date"], errors="coerce")
    work = work.dropna(subset=["invoice_date"])
    work["year_month"] = work["invoice_date"].dt.to_period("M").dt.to_timestamp()
    monthly = work.groupby("year_month")["total_amount_inr"].sum()
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(monthly.index, monthly.values / 1_000_00, color=NAVY, linewidth=2)
    ax.fill_between(monthly.index, monthly.values / 1_000_00, color=GOLD, alpha=0.25)
    ax.set_title("Monthly invoiced spend")
    ax.set_ylabel("INR lakh")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _department_spend(tables: dict[str, pd.DataFrame], path: Path) -> Path:
    invoices = tables["invoices"].drop_duplicates("invoice_id")
    orders = tables["purchase_orders"][["po_id", "department"]]
    work = invoices.merge(orders, on="po_id", how="left")
    work["department"] = work["department"].fillna("Non-PO")
    work["spend"] = pd.to_numeric(work["total_amount_inr"], errors="coerce").fillna(0).clip(lower=0)
    summary = work.groupby("department")["spend"].sum().sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(summary.index, summary.values / 1_000_00, color=TEAL)
    ax.set_xlabel("INR lakh")
    ax.set_title("Invoiced spend by department")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _risk_distribution(scores: pd.DataFrame, path: Path) -> Path:
    order = ["Low", "Medium", "High", "Critical"]
    counts = scores["risk_category"].value_counts().reindex(order).fillna(0)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(counts.index, counts.values, color=[TEAL, GOLD, "#B26A3A", "#8C2F39"])
    ax.set_title("Vendor risk categories")
    ax.set_ylabel("Vendors")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _alerts_by_rule(alerts: pd.DataFrame, path: Path) -> Path:
    if alerts.empty:
        return path
    counts = alerts["rule_code"].value_counts().sort_values()
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.barh(counts.index, counts.values, color=NAVY)
    ax.set_xlabel("Alerts")
    ax.set_title("Alerts by screening rule")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _benford(distribution: pd.DataFrame, path: Path) -> Path:
    work = distribution[distribution["population"] == "non_recurring_invoices"]
    if work.empty:
        work = distribution
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(work["digit"] - 0.15, work["observed_share"], width=0.3, label="Observed", color=NAVY)
    ax.bar(work["digit"] + 0.15, work["expected_share"], width=0.3, label="Benford", color=GOLD)
    ax.set_xticks(range(1, 10))
    ax.set_title("First-digit distribution, non-recurring invoices")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _pareto(vendor_spend: pd.DataFrame, path: Path) -> Path:
    top = vendor_spend.head(15)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    sns.barplot(data=top, x="vendor_id", y="spend_share", color=NAVY, ax=ax)
    ax.set_title("Top 15 vendors by share of positive invoice spend")
    ax.tick_params(axis="x", rotation=60)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _amount_hist(invoices: pd.DataFrame, path: Path) -> Path:
    amounts = pd.to_numeric(invoices.drop_duplicates("invoice_id")["total_amount_inr"], errors="coerce")
    amounts = amounts[amounts > 0]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(amounts.clip(upper=amounts.quantile(0.98)), bins=30, color=TEAL, edgecolor="white")
    ax.set_title("Invoice totals, clipped at the 98th percentile for display")
    ax.set_xlabel("INR")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
