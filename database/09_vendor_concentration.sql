-- Pareto spend, category HHI, and department-month totals.
-- HHI is the sum of squared spend shares within the vendor category.
-- HHI points multiply that share-based index by 10,000.

CREATE OR REPLACE VIEW vw_vendor_pareto AS
WITH spend AS (
    SELECT
        invoice.vendor_id,
        vendor.vendor_category,
        SUM(CASE WHEN invoice.total_amount_inr > 0 THEN invoice.total_amount_inr ELSE 0 END) AS spend_inr
    FROM invoices AS invoice
    JOIN vendors AS vendor ON vendor.vendor_id = invoice.vendor_id
    GROUP BY invoice.vendor_id, vendor.vendor_category
),
ranked AS (
    SELECT
        *,
        spend_inr / NULLIF(SUM(spend_inr) OVER (), 0) AS spend_share,
        SUM(spend_inr) OVER (ORDER BY spend_inr DESC, vendor_id) / NULLIF(SUM(spend_inr) OVER (), 0) AS cumulative_share
    FROM spend
)
SELECT
    vendor_id,
    vendor_category,
    ROUND(spend_inr, 2) AS spend_inr,
    ROUND(spend_share::NUMERIC, 6) AS spend_share,
    ROUND(cumulative_share::NUMERIC, 6) AS cumulative_share,
    cumulative_share <= 0.80 AS pareto_within_80_percent
FROM ranked;

CREATE OR REPLACE VIEW vw_category_hhi AS
WITH shares AS (
    SELECT
        vendor_category,
        spend_inr,
        spend_inr / NULLIF(SUM(spend_inr) OVER (PARTITION BY vendor_category), 0) AS category_share
    FROM vw_vendor_pareto
)
SELECT
    vendor_category,
    COUNT(*) AS vendor_count,
    ROUND(SUM(spend_inr), 2) AS spend_inr,
    ROUND(SUM(POWER(category_share, 2))::NUMERIC, 6) AS hhi,
    ROUND((SUM(POWER(category_share, 2)) * 10000)::NUMERIC, 2) AS hhi_points
FROM shares
GROUP BY vendor_category;

CREATE OR REPLACE VIEW vw_department_monthly_spend AS
SELECT
    COALESCE(po.department, 'Non-PO') AS department,
    TO_CHAR(invoice.invoice_date, 'YYYY-MM') AS year_month,
    ROUND(SUM(CASE WHEN invoice.total_amount_inr > 0 THEN invoice.total_amount_inr ELSE 0 END), 2) AS spend_inr
FROM invoices AS invoice
LEFT JOIN purchase_orders AS po ON po.po_id = invoice.po_id
GROUP BY COALESCE(po.department, 'Non-PO'), TO_CHAR(invoice.invoice_date, 'YYYY-MM');
