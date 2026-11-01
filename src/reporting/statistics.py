"""Statistical screens. These outputs are review aids, not fraud conclusions."""

from __future__ import annotations

import math

import pandas as pd
from scipy import stats

BENFORD_EXPECTED = {digit: math.log10(1 + 1 / digit) for digit in range(1, 10)}


def first_significant_digit(amount: float) -> int | None:
    if amount is None or pd.isna(amount) or float(amount) <= 0:
        return None
    exponent = math.floor(math.log10(float(amount)))
    digit = int(float(amount) / (10 ** exponent))
    if digit < 1 or digit > 9:
        return None
    return digit


def _population_mask(invoices: pd.DataFrame, config: dict) -> pd.Series:
    amounts = pd.to_numeric(invoices["total_amount_inr"], errors="coerce")
    item = invoices["item_code"].astype(str)
    recurring = item.str.endswith("-REC")
    petty = item.str.startswith("PTC-")
    minimum = float(config["thresholds"]["benford_min_amount_inr"])
    return amounts.ge(minimum) & ~recurring & ~petty & invoices["status"].astype(str).ne("UNKNOWN")


def benford_analysis(frame: pd.DataFrame, amount_column: str, population_name: str, config: dict, mask: pd.Series | None = None) -> dict:
    """Compare a first-digit distribution with Benford's Law.

    A deviation is a screening result. It does not establish manipulation.
    """
    amounts = pd.to_numeric(frame[amount_column], errors="coerce")
    if mask is None:
        mask = amounts.ge(float(config["thresholds"]["benford_min_amount_inr"]))
    selected = amounts[mask.fillna(False)]
    digits = [first_significant_digit(value) for value in selected if first_significant_digit(value) is not None]
    minimum = int(config["thresholds"]["benford_min_sample_size"])
    observed_counts = {digit: digits.count(digit) for digit in range(1, 10)}
    sample_size = len(digits)
    rows = []
    for digit in range(1, 10):
        expected_share = BENFORD_EXPECTED[digit]
        observed_share = (observed_counts[digit] / sample_size) if sample_size else 0.0
        rows.append(
            {
                "population": population_name,
                "digit": digit,
                "observed_count": observed_counts[digit],
                "observed_share": round(observed_share, 6),
                "expected_share": round(expected_share, 6),
                "expected_count": round(sample_size * expected_share, 4),
                "absolute_deviation": round(abs(observed_share - expected_share), 6),
            }
        )
    distribution = pd.DataFrame(rows)
    mad = float(distribution["absolute_deviation"].mean()) if sample_size else None
    if sample_size < minimum:
        return {
            "population": population_name,
            "sample_size": sample_size,
            "minimum_sample_size": minimum,
            "applicable": False,
            "chi_square": None,
            "p_value": None,
            "mad": None if mad is None else round(mad, 6),
            "conformity_band": "not_applicable",
            "limitation": (
                f"{population_name} has {sample_size} usable amounts, below the minimum of {minimum}. "
                "Benford's Law was not tested."
            ),
            "distribution": distribution,
        }
    expected = [sample_size * BENFORD_EXPECTED[digit] for digit in range(1, 10)]
    observed = [observed_counts[digit] for digit in range(1, 10)]
    chi_square, p_value = stats.chisquare(observed, expected)
    return {
        "population": population_name,
        "sample_size": sample_size,
        "minimum_sample_size": minimum,
        "applicable": True,
        "chi_square": round(float(chi_square), 4),
        "p_value": float(p_value),
        "mad": round(mad, 6),
        "conformity_band": _mad_band(mad),
        "limitation": (
            "Mean absolute deviation bands follow a common audit heuristic (close, acceptable, marginal, nonconformity). "
            "They are not a legal or statistical proof of fraud. Capped, priced-from-a-catalogue, or recurring amounts are poor Benford populations."
        ),
        "distribution": distribution,
    }


def _mad_band(mad: float) -> str:
    if mad < 0.006:
        return "close_conformity"
    if mad < 0.012:
        return "acceptable_conformity"
    if mad < 0.015:
        return "marginal_conformity"
    return "nonconformity"


def invoice_benford(invoices: pd.DataFrame, config: dict) -> dict:
    work = invoices.drop_duplicates("invoice_id")
    return benford_analysis(work, "total_amount_inr", "non_recurring_invoices", config, _population_mask(work, config))


def expense_benford(expenses: pd.DataFrame, config: dict) -> dict:
    """Contrast case. Expense policies cap many claims, so Benford is a weak fit."""
    work = expenses.drop_duplicates("expense_id")
    amounts = pd.to_numeric(work["amount_inr"], errors="coerce")
    mask = amounts.ge(float(config["thresholds"]["benford_min_amount_inr"]))
    result = benford_analysis(work, "amount_inr", "employee_expenses", config, mask)
    result["limitation"] = (
        "Employee expenses are bounded by category thresholds and receipt rules. "
        "A Benford deviation in this population is expected to be ambiguous and is not used as an alert."
    )
    return result


def statistical_outliers(invoices: pd.DataFrame, vendors: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Category-adjusted z-score, IQR, and modified z-score screens."""
    work = invoices.drop_duplicates("invoice_id").merge(
        vendors[["vendor_id", "vendor_category"]],
        on="vendor_id",
        how="left",
    )
    work["total_amount_inr"] = pd.to_numeric(work["total_amount_inr"], errors="coerce")
    work = work[work["total_amount_inr"] > 0]
    minimum = int(config["thresholds"]["outlier_min_group_size"])
    z_cutoff = float(config["thresholds"]["zscore_cutoff"])
    modified_cutoff = float(config["thresholds"]["modified_zscore_cutoff"])
    iqr_multiplier = float(config["thresholds"]["iqr_multiplier"])
    rows = []
    for category, group in work.groupby("vendor_category", sort=True):
        if len(group) < minimum:
            continue
        values = group["total_amount_inr"].astype(float)
        mean = float(values.mean())
        std = float(values.std(ddof=1))
        median = float(values.median())
        mad = float((values - median).abs().median())
        q1 = float(values.quantile(0.25))
        q3 = float(values.quantile(0.75))
        fence_low = q1 - iqr_multiplier * (q3 - q1)
        fence_high = q3 + iqr_multiplier * (q3 - q1)
        for _, row in group.iterrows():
            amount = float(row["total_amount_inr"])
            z_score = None if std == 0 else (amount - mean) / std
            modified = None if mad == 0 else 0.6745 * (amount - median) / mad
            iqr_flag = amount < fence_low or amount > fence_high
            z_flag = z_score is not None and abs(z_score) > z_cutoff
            modified_flag = modified is not None and abs(modified) > modified_cutoff
            if not (iqr_flag or z_flag or modified_flag):
                continue
            rows.append(
                {
                    "invoice_id": row["invoice_id"],
                    "vendor_id": row["vendor_id"],
                    "vendor_category": category,
                    "total_amount_inr": round(amount, 2),
                    "group_size": int(len(group)),
                    "z_score": None if z_score is None else round(z_score, 4),
                    "modified_z_score": None if modified is None else round(modified, 4),
                    "iqr_outlier": bool(iqr_flag),
                    "zscore_outlier": bool(z_flag),
                    "modified_z_outlier": bool(modified_flag),
                    "note": "Statistical outlier inside the vendor category. This is not a fraud alert.",
                }
            )
    columns = [
        "invoice_id",
        "vendor_id",
        "vendor_category",
        "total_amount_inr",
        "group_size",
        "z_score",
        "modified_z_score",
        "iqr_outlier",
        "zscore_outlier",
        "modified_z_outlier",
        "note",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values(["vendor_category", "invoice_id"]).reset_index(drop=True)
