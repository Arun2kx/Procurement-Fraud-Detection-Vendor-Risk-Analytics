"""Transparent 0–100 vendor risk score.

Weights and anchors live in the YAML configuration. They are illustrative
screening weights, not coefficients fitted to a loss history.
"""

from __future__ import annotations

import json

import pandas as pd
from sklearn.ensemble import IsolationForest

from src.utils.config import validate_risk_weights

FACTORS = (
    "duplicate_invoice_rate",
    "dispute_rate",
    "price_volatility",
    "split_purchase_involvement",
    "po_approval_violations",
    "payment_anomaly_rate",
    "spend_concentration",
)


def classify_risk(score: float, config: dict) -> str:
    bounds = config["risk_categories"]
    if score <= float(bounds["low_max"]):
        return "Low"
    if score <= float(bounds["medium_max"]):
        return "Medium"
    if score <= float(bounds["high_max"]):
        return "High"
    return "Critical"


def _scale(raw: float, anchor: float) -> float:
    if anchor <= 0:
        return 0.0
    return max(0.0, min(100.0, float(raw) / float(anchor) * 100.0))


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def score_vendors(
    tables: dict[str, pd.DataFrame],
    alerts: pd.DataFrame,
    split_clusters: pd.DataFrame,
    volatility: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """Score every vendor from observable rates. Ground truth is not an input."""
    weights = {key: float(value) for key, value in config["risk_weights"].items()}
    validate_risk_weights(weights)
    anchors = config["risk_factor_anchors"]
    vendors = tables["vendors"][["vendor_id", "vendor_name", "vendor_category", "vendor_status"]].drop_duplicates("vendor_id")
    invoices = tables["invoices"].drop_duplicates("invoice_id").copy()
    invoices["total_amount_inr"] = pd.to_numeric(invoices["total_amount_inr"], errors="coerce")
    orders = tables["purchase_orders"].drop_duplicates("po_id")
    payments = tables["payments"].drop_duplicates("payment_id")
    approvals = tables["approval_records"]
    employees = tables["employees"].drop_duplicates("employee_id")

    dup_rules = {"EXACT_DUP_INVOICE", "NEAR_TIME_DUP_INVOICE", "FUZZY_DUP_INVOICE"}
    pay_rules = {"DUP_PAYMENT", "EARLY_PAYMENT", "PAYMENT_MISMATCH", "LATE_PAYMENT"}
    dup_ids = set(alerts.loc[alerts["rule_code"].isin(dup_rules), "entity_id"].astype(str)) if not alerts.empty else set()
    pay_ids = set(alerts.loc[alerts["rule_code"].isin(pay_rules), "entity_id"].astype(str)) if not alerts.empty else set()
    split_ids = set()
    if not split_clusters.empty:
        split_ids = set(split_clusters.loc[split_clusters["disposition"] == "insufficient_approval", "po_id"].astype(str))
    violation_ids = set()
    if not alerts.empty:
        violation_ids = set(
            alerts.loc[alerts["rule_code"].isin({"PO_MISSING_APPROVAL", "PO_APPROVAL_LIMIT_BREACH"}), "entity_id"].astype(str)
        )
    self_po = approvals[
        (approvals["entity_type"] == "purchase_order")
        & (approvals["decision"] == "Approved")
    ].merge(
        orders[["po_id", "requestor_employee_id", "vendor_id"]],
        left_on="entity_id",
        right_on="po_id",
        how="inner",
    )
    self_po = self_po[self_po["approver_employee_id"] == self_po["requestor_employee_id"]]
    violation_ids.update(self_po["po_id"].astype(str))

    cv_lookup = {}
    if not volatility.empty:
        eligible = volatility[volatility["sufficient_history"] == True]  # noqa: E712
        if not eligible.empty:
            cv_lookup = eligible.groupby("vendor_id")["cv"].max().to_dict()

    positive_spend = invoices["total_amount_inr"].where(invoices["total_amount_inr"] > 0, 0)
    invoices = invoices.assign(_spend=positive_spend)
    total_spend = float(invoices["_spend"].sum())
    vendor_spend = invoices.groupby("vendor_id")["_spend"].sum().to_dict()

    rows = []
    for _, vendor in vendors.sort_values("vendor_id").iterrows():
        vendor_id = str(vendor["vendor_id"])
        vendor_invoices = invoices[invoices["vendor_id"] == vendor_id]
        vendor_orders = orders[orders["vendor_id"] == vendor_id]
        vendor_payments = payments[payments["vendor_id"] == vendor_id]
        invoice_count = int(vendor_invoices["invoice_id"].nunique())
        po_count = int(vendor_orders["po_id"].nunique())
        payment_count = int(vendor_payments["payment_id"].nunique())
        duplicate_rate = _rate(vendor_invoices["invoice_id"].astype(str).isin(dup_ids).sum(), invoice_count)
        dispute_rate = _rate(int(vendor_invoices["dispute_flag"].astype(bool).sum()) if invoice_count else 0, invoice_count)
        cv = float(cv_lookup.get(vendor_id, 0.0) or 0.0)
        split_share = _rate(vendor_orders["po_id"].astype(str).isin(split_ids).sum(), po_count)
        violation_share = _rate(vendor_orders["po_id"].astype(str).isin(violation_ids).sum(), po_count)
        payment_rate = _rate(vendor_payments["payment_id"].astype(str).isin(pay_ids).sum(), payment_count)
        share = (vendor_spend.get(vendor_id, 0.0) / total_spend) if total_spend else 0.0
        concentration_raw = max(0.0, share - float(anchors["spend_share_floor"])) / float(anchors["spend_share_span"])

        factor_scores = {
            "duplicate_invoice_rate": _scale(duplicate_rate, anchors["duplicate_invoice_rate"]),
            "dispute_rate": _scale(dispute_rate, anchors["dispute_rate"]),
            "price_volatility": _scale(cv, anchors["price_volatility_cv"]),
            "split_purchase_involvement": _scale(split_share, anchors["split_purchase_share"]),
            "po_approval_violations": _scale(violation_share, anchors["po_approval_violation_share"]),
            "payment_anomaly_rate": _scale(payment_rate, anchors["payment_anomaly_rate"]),
            "spend_concentration": _scale(concentration_raw, 1.0),
        }
        points = {name: round(weights[name] * factor_scores[name], 4) for name in FACTORS}
        score = round(sum(points.values()), 2)
        category = classify_risk(score, config)
        supporting = []
        if not alerts.empty:
            supporting = sorted(alerts.loc[alerts["vendor_id"].astype(str) == vendor_id, "alert_id"].astype(str))
        explanation = _explain(score, category, points, {
            "duplicate_invoice_rate": duplicate_rate,
            "dispute_rate": dispute_rate,
            "price_volatility_cv": cv,
            "split_purchase_share": split_share,
            "po_approval_violation_share": violation_share,
            "payment_anomaly_rate": payment_rate,
            "spend_share": share,
        }, invoice_count)
        row = {
            "vendor_id": vendor_id,
            "vendor_name": vendor["vendor_name"],
            "vendor_category": vendor["vendor_category"],
            "vendor_status": vendor["vendor_status"],
            "invoice_count": invoice_count,
            "po_count": po_count,
            "payment_count": payment_count,
            "spend_inr": round(float(vendor_spend.get(vendor_id, 0.0)), 2),
            "spend_share": round(share, 6),
            "risk_score": score,
            "risk_category": category,
            "explanation": explanation,
            "supporting_alert_ids": "|".join(supporting),
            "low_sample": invoice_count < 5,
        }
        for name in FACTORS:
            row[f"raw_{name}"] = round(
                {
                    "duplicate_invoice_rate": duplicate_rate,
                    "dispute_rate": dispute_rate,
                    "price_volatility": cv,
                    "split_purchase_involvement": split_share,
                    "po_approval_violations": violation_share,
                    "payment_anomaly_rate": payment_rate,
                    "spend_concentration": share,
                }[name],
                6,
            )
            row[f"score_{name}"] = round(factor_scores[name], 4)
            row[f"points_{name}"] = points[name]
        rows.append(row)

    scored = pd.DataFrame(rows).sort_values(["risk_score", "vendor_id"], ascending=[False, True]).reset_index(drop=True)
    scored = _add_isolation_forest(scored, config)
    return scored


def _explain(score: float, category: str, points: dict[str, float], raws: dict[str, float], invoice_count: int) -> str:
    parts = [
        f"{label} {points[key]:.2f} points (observed {raws[raw_key]:.2%})"
        if raw_key != "price_volatility_cv"
        else f"{label} {points[key]:.2f} points (CV {raws[raw_key]:.2f})"
        for key, label, raw_key in (
            ("duplicate_invoice_rate", "duplicate invoices", "duplicate_invoice_rate"),
            ("dispute_rate", "disputes", "dispute_rate"),
            ("price_volatility", "price volatility", "price_volatility_cv"),
            ("split_purchase_involvement", "split purchases", "split_purchase_share"),
            ("po_approval_violations", "approval violations", "po_approval_violation_share"),
            ("payment_anomaly_rate", "payment anomalies", "payment_anomaly_rate"),
            ("spend_concentration", "spend share", "spend_share"),
        )
    ]
    sample = " Invoice history is below 5, so the rate factors are unstable." if invoice_count < 5 else ""
    return f"Score {score:.2f} ({category}). " + "; ".join(parts) + "." + sample


def _add_isolation_forest(scored: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Optional comparison. The official score does not use this flag."""
    features = [f"score_{name}" for name in FACTORS]
    matrix = scored[features].fillna(0.0)
    if len(scored) < 10 or matrix.sum().sum() == 0:
        scored["isolation_forest_flag"] = False
        scored["isolation_forest_note"] = "Not fitted because the vendor population or feature matrix is too small."
        return scored
    model = IsolationForest(
        n_estimators=200,
        contamination=0.1,
        random_state=int(config["random_seed"]),
    )
    flags = model.fit_predict(matrix)
    scored["isolation_forest_flag"] = flags == -1
    scored["isolation_forest_note"] = (
        "Unsupervised comparison only. A flag is not a risk category and is not used in the 0–100 score."
    )
    return scored


def attach_vendor_scores(alerts: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    if alerts.empty:
        return alerts
    lookup = scores.set_index("vendor_id")["risk_score"]
    updated = alerts.copy()
    updated["risk_score"] = updated["vendor_id"].map(lookup)
    return updated


def score_snapshot(scores: pd.DataFrame) -> str:
    return json.dumps(
        {
            "vendors": int(len(scores)),
            "by_category": scores["risk_category"].value_counts().to_dict() if not scores.empty else {},
        },
        sort_keys=True,
    )
