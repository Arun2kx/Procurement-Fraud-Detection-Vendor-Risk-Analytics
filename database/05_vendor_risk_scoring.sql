-- Explainable vendor risk inputs and score.
-- Weights are inserted by 01_schema.sql and are not overwritten on re-run.
-- They match config/config.example.yaml. The Python score is the pipeline source of truth.
-- Anchors match the example configuration: a 15% duplicate rate scores 100 on that factor.
-- SQL payment_anomaly_rate counts early payments and non-disputed delays over 60 days.
-- Duplicate-payment and amount-mismatch counts are in database/08_payment_analysis.sql,
-- so this SQL score is not expected to equal the Python score on every vendor.

CREATE OR REPLACE VIEW vw_vendor_risk_score AS
WITH weights AS (
    SELECT
        COALESCE(MAX(weight) FILTER (WHERE factor_name = 'duplicate_invoice_rate'), 0.22) AS w_duplicate_invoice_rate,
        COALESCE(MAX(weight) FILTER (WHERE factor_name = 'dispute_rate'), 0.10) AS w_dispute_rate,
        COALESCE(MAX(weight) FILTER (WHERE factor_name = 'price_volatility'), 0.12) AS w_price_volatility,
        COALESCE(MAX(weight) FILTER (WHERE factor_name = 'split_purchase_involvement'), 0.18) AS w_split_purchase_involvement,
        COALESCE(MAX(weight) FILTER (WHERE factor_name = 'po_approval_violations'), 0.16) AS w_po_approval_violations,
        COALESCE(MAX(weight) FILTER (WHERE factor_name = 'payment_anomaly_rate'), 0.14) AS w_payment_anomaly_rate,
        COALESCE(MAX(weight) FILTER (WHERE factor_name = 'spend_concentration'), 0.08) AS w_spend_concentration
    FROM risk_weight_config
),
invoice_stats AS (
    SELECT
        vendor_id,
        COUNT(*) AS invoice_count,
        SUM(CASE WHEN dispute_flag THEN 1 ELSE 0 END) AS disputed_count,
        SUM(CASE WHEN total_amount_inr > 0 THEN total_amount_inr ELSE 0 END) AS spend_inr
    FROM invoices
    GROUP BY vendor_id
),
duplicate_stats AS (
    SELECT vendor_id, COUNT(DISTINCT invoice_id) AS duplicate_invoices
    FROM (
        SELECT vendor_id, invoice_id FROM vw_exact_duplicate_invoices
        UNION
        SELECT vendor_id, left_invoice_id FROM vw_fuzzy_duplicate_invoices
        UNION
        SELECT vendor_id, right_invoice_id FROM vw_fuzzy_duplicate_invoices
        UNION
        SELECT vendor_id, left_invoice_id FROM vw_near_time_duplicate_invoices
        UNION
        SELECT vendor_id, right_invoice_id FROM vw_near_time_duplicate_invoices
    ) AS combined
    GROUP BY vendor_id
),
price_stats AS (
    SELECT vendor_id, MAX(cv) AS max_cv
    FROM (
        SELECT
            vendor_id,
            item_code,
            COUNT(*) AS observations,
            STDDEV_SAMP(unit_price_inr) / NULLIF(AVG(unit_price_inr), 0) AS cv
        FROM invoices
        WHERE unit_price_inr > 0
        GROUP BY vendor_id, item_code
        HAVING COUNT(*) >= 6
    ) AS item_cv
    GROUP BY vendor_id
),
po_stats AS (
    SELECT vendor_id, COUNT(*) AS po_count
    FROM purchase_orders
    GROUP BY vendor_id
),
split_stats AS (
    SELECT vendor_id, COUNT(DISTINCT po_id) AS split_po_count
    FROM vw_split_purchase_clusters
    WHERE disposition = 'insufficient_approval'
    GROUP BY vendor_id
),
violation_stats AS (
    SELECT vendor_id, COUNT(DISTINCT po_id) AS violation_count
    FROM (
        SELECT po.vendor_id, po.po_id
        FROM purchase_orders AS po
        LEFT JOIN approval_records AS approval
            ON approval.entity_type = 'purchase_order'
           AND approval.entity_id = po.po_id
        WHERE po.status IN ('Approved', 'Closed')
          AND po.po_amount_inr >= 50000
          AND approval.approval_id IS NULL
        UNION
        SELECT po.vendor_id, po.po_id
        FROM purchase_orders AS po
        JOIN approval_records AS approval
            ON approval.entity_type = 'purchase_order'
           AND approval.entity_id = po.po_id
           AND approval.decision = 'Approved'
        JOIN employees AS employee ON employee.employee_id = approval.approver_employee_id
        WHERE po.status IN ('Approved', 'Closed')
        GROUP BY po.vendor_id, po.po_id, po.po_amount_inr
        HAVING MAX(employee.approval_limit_inr) < po.po_amount_inr
        UNION
        SELECT po.vendor_id, po.po_id
        FROM purchase_orders AS po
        JOIN approval_records AS approval
            ON approval.entity_type = 'purchase_order'
           AND approval.entity_id = po.po_id
           AND approval.decision = 'Approved'
           AND approval.approver_employee_id = po.requestor_employee_id
    ) AS violations
    GROUP BY vendor_id
),
payment_stats AS (
    SELECT
        payment.vendor_id,
        COUNT(*) AS payment_count,
        COUNT(*) FILTER (
            WHERE invoice.invoice_id IS NOT NULL
              AND (
                    payment.payment_date < invoice.invoice_date
                    OR (
                        invoice.dispute_flag = FALSE
                        AND payment.payment_date > invoice.due_date + 60
                    )
              )
        ) AS anomalous_payments
    FROM payments AS payment
    LEFT JOIN invoices AS invoice ON invoice.invoice_id = payment.invoice_id
    WHERE payment.status = 'Completed'
    GROUP BY payment.vendor_id
),
spend_total AS (
    SELECT COALESCE(SUM(spend_inr), 0) AS total_spend FROM invoice_stats
),
scored AS (
    SELECT
        vendor.vendor_id,
        vendor.vendor_name,
        vendor.vendor_category,
        COALESCE(invoice_stats.invoice_count, 0) AS invoice_count,
        COALESCE(invoice_stats.spend_inr, 0) AS spend_inr,
        COALESCE(duplicate_stats.duplicate_invoices, 0)::NUMERIC
            / NULLIF(invoice_stats.invoice_count, 0) AS duplicate_invoice_rate,
        COALESCE(invoice_stats.disputed_count, 0)::NUMERIC
            / NULLIF(invoice_stats.invoice_count, 0) AS dispute_rate,
        COALESCE(price_stats.max_cv, 0) AS price_volatility_cv,
        COALESCE(split_stats.split_po_count, 0)::NUMERIC / NULLIF(po_stats.po_count, 0) AS split_purchase_share,
        COALESCE(violation_stats.violation_count, 0)::NUMERIC / NULLIF(po_stats.po_count, 0) AS approval_violation_share,
        COALESCE(payment_stats.anomalous_payments, 0)::NUMERIC
            / NULLIF(payment_stats.payment_count, 0) AS payment_anomaly_rate,
        COALESCE(invoice_stats.spend_inr, 0) / NULLIF(spend_total.total_spend, 0) AS spend_share
    FROM vendors AS vendor
    CROSS JOIN spend_total
    LEFT JOIN invoice_stats ON invoice_stats.vendor_id = vendor.vendor_id
    LEFT JOIN duplicate_stats ON duplicate_stats.vendor_id = vendor.vendor_id
    LEFT JOIN price_stats ON price_stats.vendor_id = vendor.vendor_id
    LEFT JOIN po_stats ON po_stats.vendor_id = vendor.vendor_id
    LEFT JOIN split_stats ON split_stats.vendor_id = vendor.vendor_id
    LEFT JOIN violation_stats ON violation_stats.vendor_id = vendor.vendor_id
    LEFT JOIN payment_stats ON payment_stats.vendor_id = vendor.vendor_id
)
SELECT
    scored.*,
    LEAST(100, COALESCE(scored.duplicate_invoice_rate, 0) / 0.15 * 100) AS score_duplicate_invoice_rate,
    LEAST(100, COALESCE(scored.dispute_rate, 0) / 0.20 * 100) AS score_dispute_rate,
    LEAST(100, COALESCE(scored.price_volatility_cv, 0) / 0.50 * 100) AS score_price_volatility,
    LEAST(100, COALESCE(scored.split_purchase_share, 0) / 0.25 * 100) AS score_split_purchase_involvement,
    LEAST(100, COALESCE(scored.approval_violation_share, 0) / 0.10 * 100) AS score_po_approval_violations,
    LEAST(100, COALESCE(scored.payment_anomaly_rate, 0) / 0.15 * 100) AS score_payment_anomaly_rate,
    LEAST(100, GREATEST(0, COALESCE(scored.spend_share, 0) - 0.05) / 0.20 * 100) AS score_spend_concentration,
    ROUND((
        LEAST(100, COALESCE(scored.duplicate_invoice_rate, 0) / 0.15 * 100) * weights.w_duplicate_invoice_rate
        + LEAST(100, COALESCE(scored.dispute_rate, 0) / 0.20 * 100) * weights.w_dispute_rate
        + LEAST(100, COALESCE(scored.price_volatility_cv, 0) / 0.50 * 100) * weights.w_price_volatility
        + LEAST(100, COALESCE(scored.split_purchase_share, 0) / 0.25 * 100) * weights.w_split_purchase_involvement
        + LEAST(100, COALESCE(scored.approval_violation_share, 0) / 0.10 * 100) * weights.w_po_approval_violations
        + LEAST(100, COALESCE(scored.payment_anomaly_rate, 0) / 0.15 * 100) * weights.w_payment_anomaly_rate
        + LEAST(100, GREATEST(0, COALESCE(scored.spend_share, 0) - 0.05) / 0.20 * 100) * weights.w_spend_concentration
    )::NUMERIC, 2) AS risk_score
FROM scored
CROSS JOIN weights;
