-- Duplicate invoice screens.
-- Exact: same vendor and invoice number, ignoring letter case only.
-- Normalised: punctuation and separators removed.
-- Edit distance: one-character difference, excluding a short step in the same numeric series.
-- The Levenshtein function below is the portable option. pg_trgm is not required.

CREATE OR REPLACE FUNCTION procureguard_levenshtein(left_text TEXT, right_text TEXT)
RETURNS INTEGER
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    left_len INTEGER := LENGTH(left_text);
    right_len INTEGER := LENGTH(right_text);
    previous INTEGER[];
    current_row INTEGER[];
    i INTEGER;
    j INTEGER;
    substitution INTEGER;
BEGIN
    IF left_text IS NULL OR right_text IS NULL THEN
        RETURN NULL;
    END IF;
    IF left_text = right_text THEN
        RETURN 0;
    END IF;
    IF left_len = 0 THEN
        RETURN right_len;
    END IF;
    IF right_len = 0 THEN
        RETURN left_len;
    END IF;
    previous := ARRAY(SELECT g FROM generate_series(0, right_len) AS g);
    FOR i IN 1..left_len LOOP
        current_row := ARRAY[i];
        FOR j IN 1..right_len LOOP
            substitution := CASE WHEN SUBSTRING(left_text FROM i FOR 1) = SUBSTRING(right_text FROM j FOR 1) THEN 0 ELSE 1 END;
            current_row := current_row || LEAST(previous[j + 1] + 1, current_row[j] + 1, previous[j] + substitution);
        END LOOP;
        previous := current_row;
    END LOOP;
    RETURN previous[right_len + 1];
END;
$$;

CREATE OR REPLACE VIEW vw_invoice_number_keys AS
SELECT
    invoice_id,
    vendor_id,
    invoice_number,
    invoice_date,
    item_code,
    total_amount_inr,
    UPPER(BTRIM(invoice_number)) AS casefold_number,
    UPPER(REGEXP_REPLACE(invoice_number, '[^A-Za-z0-9]', '', 'g')) AS norm_number
FROM invoices
WHERE total_amount_inr > 0;

CREATE OR REPLACE VIEW vw_exact_duplicate_invoices AS
WITH counted AS (
    SELECT
        vendor_id,
        casefold_number,
        COUNT(*) AS copy_count
    FROM vw_invoice_number_keys
    WHERE casefold_number <> ''
    GROUP BY vendor_id, casefold_number
    HAVING COUNT(*) > 1
)
SELECT invoice.*
FROM vw_invoice_number_keys AS invoice
JOIN counted
    ON counted.vendor_id = invoice.vendor_id
   AND counted.casefold_number = invoice.casefold_number;

CREATE OR REPLACE VIEW vw_fuzzy_duplicate_invoices AS
WITH keys AS (
    SELECT
        *,
        REGEXP_REPLACE(norm_number, '[0-9]+$', '') AS series_prefix,
        CASE
            WHEN norm_number ~ '[0-9]$' THEN SUBSTRING(norm_number FROM '[0-9]+$')::NUMERIC
            ELSE NULL
        END AS series_number
    FROM vw_invoice_number_keys
)
SELECT
    left_row.vendor_id,
    left_row.invoice_id AS left_invoice_id,
    right_row.invoice_id AS right_invoice_id,
    left_row.invoice_number AS left_invoice_number,
    right_row.invoice_number AS right_invoice_number,
    CASE
        WHEN left_row.norm_number = right_row.norm_number THEN 'normalised_invoice_number'
        ELSE 'edit_distance'
    END AS match_type
FROM keys AS left_row
JOIN keys AS right_row
    ON right_row.vendor_id = left_row.vendor_id
   AND right_row.invoice_id > left_row.invoice_id
WHERE left_row.casefold_number <> right_row.casefold_number
  AND ABS(left_row.total_amount_inr - right_row.total_amount_inr)
      / GREATEST(left_row.total_amount_inr, right_row.total_amount_inr) <= 0.02
  AND (
        left_row.norm_number = right_row.norm_number
        OR (
            ABS(left_row.invoice_date - right_row.invoice_date) <= 21
            AND procureguard_levenshtein(left_row.norm_number, right_row.norm_number) = 1
            AND NOT (
                left_row.series_prefix = right_row.series_prefix
                AND left_row.series_number IS NOT NULL
                AND ABS(left_row.series_number - right_row.series_number) <= 80
            )
        )
  );

CREATE OR REPLACE VIEW vw_near_time_duplicate_invoices AS
WITH keys AS (
    SELECT
        *,
        REGEXP_REPLACE(norm_number, '[0-9]+$', '') AS series_prefix,
        CASE
            WHEN norm_number ~ '[0-9]$' THEN SUBSTRING(norm_number FROM '[0-9]+$')::NUMERIC
            ELSE NULL
        END AS series_number
    FROM vw_invoice_number_keys
    WHERE item_code NOT LIKE '%-REC'
)
SELECT
    left_row.vendor_id,
    left_row.invoice_id AS left_invoice_id,
    right_row.invoice_id AS right_invoice_id,
    left_row.invoice_number AS left_invoice_number,
    right_row.invoice_number AS right_invoice_number,
    ABS(left_row.invoice_date - right_row.invoice_date) AS day_gap,
    left_row.total_amount_inr AS left_total_inr,
    right_row.total_amount_inr AS right_total_inr
FROM keys AS left_row
JOIN keys AS right_row
    ON right_row.vendor_id = left_row.vendor_id
   AND right_row.invoice_id > left_row.invoice_id
   AND right_row.item_code = left_row.item_code
WHERE ABS(left_row.invoice_date - right_row.invoice_date) <= 5
  AND left_row.casefold_number <> right_row.casefold_number
  AND left_row.norm_number <> right_row.norm_number
  AND ABS(left_row.total_amount_inr - right_row.total_amount_inr)
      / GREATEST(left_row.total_amount_inr, right_row.total_amount_inr) <= 0.01
  AND procureguard_levenshtein(left_row.norm_number, right_row.norm_number) > 1
  AND NOT (
        left_row.series_prefix = right_row.series_prefix
        AND left_row.series_number IS NOT NULL
        AND ABS(left_row.series_number - right_row.series_number) <= 80
  );
