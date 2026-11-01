-- Master review view. Alert counts come from audit_alerts_log and are zero
-- until the Python pipeline has loaded that table.
-- An alert remains a screening result. Review status is not a fraud conclusion.

CREATE OR REPLACE VIEW vw_fraud_risk_master AS
WITH alert_rollup AS (
    SELECT
        vendor_id,
        COUNT(*) AS alert_count,
        COUNT(*) FILTER (WHERE severity IN ('High', 'Critical')) AS high_or_critical_alerts,
        COALESCE(SUM(estimated_exposure_inr), 0) AS potential_exposure_inr,
        COUNT(*) FILTER (WHERE review_status = 'Pending Review') AS pending_review_count
    FROM audit_alerts_log
    WHERE vendor_id IS NOT NULL
    GROUP BY vendor_id
)
SELECT
    risk.vendor_id,
    risk.vendor_name,
    risk.vendor_category,
    risk.invoice_count,
    risk.spend_inr,
    risk.duplicate_invoice_rate,
    risk.dispute_rate,
    risk.price_volatility_cv,
    risk.split_purchase_share,
    risk.approval_violation_share,
    risk.payment_anomaly_rate,
    risk.spend_share,
    risk.risk_score,
    CASE
        WHEN risk.risk_score <= 25 THEN 'Low'
        WHEN risk.risk_score <= 50 THEN 'Medium'
        WHEN risk.risk_score <= 75 THEN 'High'
        ELSE 'Critical'
    END AS risk_category,
    COALESCE(alert_rollup.alert_count, 0) AS alert_count,
    COALESCE(alert_rollup.high_or_critical_alerts, 0) AS high_or_critical_alerts,
    COALESCE(alert_rollup.potential_exposure_inr, 0) AS potential_exposure_inr,
    COALESCE(alert_rollup.pending_review_count, 0) AS pending_review_count
FROM vw_vendor_risk_score AS risk
LEFT JOIN alert_rollup ON alert_rollup.vendor_id = risk.vendor_id;
