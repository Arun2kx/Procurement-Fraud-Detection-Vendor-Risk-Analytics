-- Payment exceptions. A disputed invoice is excluded from the delay test.
-- Two partial payments that sum to the invoice are not duplicate full payments.

CREATE OR REPLACE VIEW vw_payment_exceptions AS
WITH completed AS (
    SELECT *
    FROM payments
    WHERE status = 'Completed'
),
rolled AS (
    SELECT
        invoice_id,
        COUNT(*) AS payment_count,
        SUM(payment_amount_inr) AS payment_sum_inr,
        COUNT(*) FILTER (
            WHERE payment_amount_inr >= (
                SELECT total_amount_inr * 0.98
                FROM invoices
                WHERE invoices.invoice_id = completed.invoice_id
            )
        ) AS full_payment_count
    FROM completed
    GROUP BY invoice_id
)
SELECT
    payment.payment_id,
    payment.invoice_id,
    payment.vendor_id,
    payment.payment_date,
    payment.payment_amount_inr,
    invoice.invoice_date,
    invoice.due_date,
    invoice.total_amount_inr,
    invoice.dispute_flag,
    rolled.payment_sum_inr,
    CASE
        WHEN rolled.full_payment_count >= 2 THEN 'DUP_PAYMENT'
        WHEN payment.payment_date < invoice.invoice_date THEN 'EARLY_PAYMENT'
        WHEN invoice.dispute_flag = FALSE AND payment.payment_date > invoice.due_date + 60 THEN 'LATE_PAYMENT'
        WHEN rolled.full_payment_count < 2
             AND (
                 rolled.payment_sum_inr > invoice.total_amount_inr * 1.02
                 OR (invoice.status = 'Paid' AND rolled.payment_sum_inr < invoice.total_amount_inr * 0.98)
             ) THEN 'PAYMENT_MISMATCH'
        ELSE NULL
    END AS rule_code
FROM completed AS payment
JOIN invoices AS invoice ON invoice.invoice_id = payment.invoice_id
JOIN rolled ON rolled.invoice_id = payment.invoice_id
WHERE invoice.total_amount_inr > 0;

CREATE OR REPLACE VIEW vw_payment_alert_candidates AS
SELECT *
FROM vw_payment_exceptions
WHERE rule_code IS NOT NULL;

CREATE OR REPLACE VIEW vw_payment_ageing AS
SELECT
    invoice.invoice_id,
    invoice.vendor_id,
    invoice.invoice_date,
    invoice.due_date,
    invoice.total_amount_inr,
    invoice.status,
    COALESCE(SUM(payment.payment_amount_inr) FILTER (WHERE payment.status = 'Completed'), 0) AS paid_amount_inr,
    CASE
        WHEN invoice.status IN ('Paid', 'Disputed', 'Rejected') THEN invoice.status
        WHEN DATE '2025-03-31' <= invoice.due_date THEN 'Not yet due'
        WHEN DATE '2025-03-31' - invoice.due_date <= 30 THEN '1-30 days past due'
        WHEN DATE '2025-03-31' - invoice.due_date <= 60 THEN '31-60 days past due'
        ELSE 'More than 60 days past due'
    END AS ageing_bucket
FROM invoices AS invoice
LEFT JOIN payments AS payment ON payment.invoice_id = invoice.invoice_id
GROUP BY
    invoice.invoice_id,
    invoice.vendor_id,
    invoice.invoice_date,
    invoice.due_date,
    invoice.total_amount_inr,
    invoice.status;
