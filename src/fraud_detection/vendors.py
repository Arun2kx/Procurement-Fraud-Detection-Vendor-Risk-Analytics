"""Vendor price-volatility and dispute-rate screening."""

from __future__ import annotations

import pandas as pd

from src.fraud_detection.common import candidates_frame, evidence, rule_fields


def find_price_volatility(invoices: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Measure the coefficient of variation of unit price by vendor and item.

    Items with fewer than the configured number of observations are reported
    and are not alerted. A high coefficient of variation is a pricing-review
    indicator, not proof of overbilling.
    """
    minimum = int(config["thresholds"]["price_volatility_min_observations"])
    cutoff = float(config["thresholds"]["price_volatility_cv_threshold"])
    work = invoices.copy()
    work["unit_price_inr"] = pd.to_numeric(work["unit_price_inr"], errors="coerce")
    work["quantity"] = pd.to_numeric(work["quantity"], errors="coerce")
    work = work[(work["unit_price_inr"] > 0) & (work["quantity"] > 0)]
    metric_rows: list[dict] = []
    for (vendor_id, item_code), group in work.groupby(["vendor_id", "item_code"], sort=True):
        prices = group["unit_price_inr"]
        mean_price = float(prices.mean())
        if mean_price == 0 or len(group) < 2:
            continue
        std_price = float(prices.std(ddof=1)) if len(group) > 1 else 0.0
        cv = std_price / mean_price
        median_price = float(prices.median())
        variance = ((group["unit_price_inr"] - median_price).abs() * group["quantity"]).sum()
        metric_rows.append(
            {
                "vendor_id": vendor_id,
                "item_code": item_code,
                "observation_count": int(len(group)),
                "mean_unit_price_inr": round(mean_price, 2),
                "std_unit_price_inr": round(std_price, 2),
                "cv": round(cv, 4),
                "pricing_variance_inr": round(float(variance), 2),
                "sufficient_history": len(group) >= minimum,
            }
        )
    metrics = pd.DataFrame(metric_rows)
    if metrics.empty:
        metrics = pd.DataFrame(
            columns=[
                "vendor_id",
                "item_code",
                "observation_count",
                "mean_unit_price_inr",
                "std_unit_price_inr",
                "cv",
                "pricing_variance_inr",
                "sufficient_history",
            ]
        )
        return candidates_frame([]), metrics

    alertable = metrics[(metrics["sufficient_history"]) & (metrics["cv"] >= cutoff)]
    base = rule_fields("PRICE_VOLATILITY")
    rows: list[dict] = []
    for vendor_id, group in alertable.groupby("vendor_id", sort=True):
        # One vendor-level alert. Evidence lists each volatile item.
        top = group.sort_values("cv", ascending=False).iloc[0]
        payload = {
            "vendor_id": str(vendor_id),
            "items": group.sort_values("item_code")[
                ["item_code", "observation_count", "cv", "pricing_variance_inr"]
            ].to_dict("records"),
            "cv_threshold": cutoff,
            "min_observations": minimum,
        }
        rows.append(
            {
                **base,
                "entity_id": str(vendor_id),
                "vendor_id": str(vendor_id),
                "employee_id": "",
                "estimated_exposure_inr": round(float(group["pricing_variance_inr"].sum()), 2),
                "detection_reason": (
                    f"Unit-price coefficient of variation for {top['item_code']} is {float(top['cv']):.2f}, "
                    f"at or above {cutoff:.2f}, with at least {minimum} observations. "
                    "This measures price dispersion, not a confirmed loss."
                ),
                "supporting_evidence": evidence(payload),
            }
        )
    return candidates_frame(rows), metrics.sort_values(["vendor_id", "item_code"]).reset_index(drop=True)


def find_high_dispute_rates(invoices: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Flag vendors whose dispute rate and dispute count both clear the cutoff."""
    rate_cutoff = float(config["thresholds"]["dispute_rate_alert"])
    min_count = int(config["thresholds"]["dispute_min_count"])
    work = invoices.copy()
    work["dispute_flag"] = work["dispute_flag"].astype(bool)
    work["total_amount_inr"] = pd.to_numeric(work["total_amount_inr"], errors="coerce").fillna(0)
    base = rule_fields("HIGH_DISPUTE_RATE")
    rows: list[dict] = []
    for vendor_id, group in work.groupby("vendor_id", sort=True):
        disputed = group[group["dispute_flag"]]
        if len(group) == 0:
            continue
        rate = len(disputed) / len(group)
        if len(disputed) < min_count or rate < rate_cutoff:
            continue
        payload = {
            "vendor_id": str(vendor_id),
            "invoice_count": int(len(group)),
            "disputed_count": int(len(disputed)),
            "dispute_rate": round(rate, 4),
            "disputed_invoice_ids": [str(value) for value in sorted(disputed["invoice_id"])],
        }
        rows.append(
            {
                **base,
                "entity_id": str(vendor_id),
                "vendor_id": str(vendor_id),
                "employee_id": "",
                "estimated_exposure_inr": round(float(disputed["total_amount_inr"].clip(lower=0).sum()), 2),
                "detection_reason": (
                    "The vendor dispute rate is elevated. Disputes can be operational and are not, by themselves, fraud."
                ),
                "supporting_evidence": evidence(payload),
            }
        )
    return candidates_frame(rows)
