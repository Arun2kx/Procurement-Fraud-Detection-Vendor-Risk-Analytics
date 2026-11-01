-- First-digit screen for invoice totals.
-- Recurring contract items and petty-purchase codes are excluded because those
-- populations are bounded or repetitive. A deviation is not evidence of fraud.
-- Chi-square p-values are computed in Python. This view returns the statistic inputs.

CREATE OR REPLACE VIEW vw_benford_invoice_digits AS
WITH eligible AS (
    SELECT total_amount_inr
    FROM invoices
    WHERE total_amount_inr >= 1000
      AND item_code NOT LIKE '%-REC'
      AND item_code NOT LIKE 'PTC-%'
      AND status <> 'UNKNOWN'
),
digits AS (
    SELECT
        FLOOR(
            total_amount_inr / POWER(10, FLOOR(LOG(total_amount_inr)))
        )::INTEGER AS digit
    FROM eligible
),
observed AS (
    SELECT digit, COUNT(*) AS observed_count
    FROM digits
    WHERE digit BETWEEN 1 AND 9
    GROUP BY digit
),
expected AS (
    SELECT
        digit,
        LOG(1 + 1.0 / digit) AS expected_share
    FROM generate_series(1, 9) AS digit
),
sample AS (
    SELECT COUNT(*) AS sample_size FROM digits WHERE digit BETWEEN 1 AND 9
)
SELECT
    expected.digit,
    COALESCE(observed.observed_count, 0) AS observed_count,
    sample.sample_size,
    ROUND(COALESCE(observed.observed_count, 0)::NUMERIC / NULLIF(sample.sample_size, 0), 6) AS observed_share,
    ROUND(expected.expected_share::NUMERIC, 6) AS expected_share,
    ROUND((sample.sample_size * expected.expected_share)::NUMERIC, 4) AS expected_count
FROM expected
CROSS JOIN sample
LEFT JOIN observed ON observed.digit = expected.digit;

CREATE OR REPLACE VIEW vw_benford_invoice_summary AS
SELECT
    MAX(sample_size) AS sample_size,
    ROUND(AVG(ABS(observed_share - expected_share))::NUMERIC, 6) AS mad,
    ROUND(SUM(
        POWER(observed_count - expected_count, 2) / NULLIF(expected_count, 0)
    )::NUMERIC, 4) AS chi_square,
    CASE
        WHEN MAX(sample_size) < 100 THEN 'not_applicable'
        WHEN AVG(ABS(observed_share - expected_share)) < 0.006 THEN 'close_conformity'
        WHEN AVG(ABS(observed_share - expected_share)) < 0.012 THEN 'acceptable_conformity'
        WHEN AVG(ABS(observed_share - expected_share)) < 0.015 THEN 'marginal_conformity'
        ELSE 'nonconformity'
    END AS conformity_band
FROM vw_benford_invoice_digits;
