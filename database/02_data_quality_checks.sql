-- Data-quality findings that remain visible after constraint-valid rows are loaded.
-- Rows rejected at ingestion (invalid status, orphan keys, duplicate primary keys)
-- are not in these tables. They stay in the raw CSV files and the rejection log.

CREATE OR REPLACE VIEW vw_data_quality_findings AS
SELECT 'NULL_EMPLOYEE_EMAIL' AS check_id, 'employees' AS table_name, employee_id AS record_id, 'email' AS column_name
FROM employees
WHERE email IS NULL
UNION ALL
SELECT 'NULL_VENDOR_CITY', 'vendors', vendor_id, 'city'
FROM vendors
WHERE city IS NULL
UNION ALL
SELECT 'DUPLICATE_BANK_HASH', 'vendors', vendor_id, 'bank_account_hash'
FROM vendors
WHERE bank_account_hash IN (
    SELECT bank_account_hash FROM vendors GROUP BY bank_account_hash HAVING COUNT(*) > 1
)
UNION ALL
SELECT 'NEGATIVE_AMOUNT', 'invoices', invoice_id, 'total_amount_inr'
FROM invoices
WHERE total_amount_inr < 0 OR invoice_amount_inr < 0 OR tax_amount_inr < 0 OR unit_price_inr < 0
UNION ALL
SELECT 'NEGATIVE_AMOUNT', 'employee_expenses', expense_id, 'amount_inr'
FROM employee_expenses
WHERE amount_inr < 0
UNION ALL
SELECT 'INVALID_DATE_SEQUENCE', 'invoices', invoice_id, 'due_date'
FROM invoices
WHERE due_date < invoice_date
UNION ALL
SELECT 'INVOICE_MATH_MISMATCH', 'invoices', invoice_id, 'total_amount_inr'
FROM invoices
WHERE ABS((invoice_amount_inr + tax_amount_inr) - total_amount_inr) > 0.05
UNION ALL
SELECT 'TRANSACTION_BEFORE_HIRE', 'employee_expenses', expense.expense_id, 'expense_date'
FROM employee_expenses AS expense
JOIN employees AS employee ON employee.employee_id = expense.employee_id
WHERE expense.expense_date < employee.hire_date
UNION ALL
SELECT 'ORPHAN_APPROVAL_ENTITY', 'approval_records', approval.approval_id, 'entity_id'
FROM approval_records AS approval
LEFT JOIN purchase_orders AS po
    ON approval.entity_type = 'purchase_order' AND approval.entity_id = po.po_id
LEFT JOIN invoices AS invoice
    ON approval.entity_type = 'invoice' AND approval.entity_id = invoice.invoice_id
LEFT JOIN employee_expenses AS expense
    ON approval.entity_type = 'employee_expense' AND approval.entity_id = expense.expense_id
WHERE po.po_id IS NULL AND invoice.invoice_id IS NULL AND expense.expense_id IS NULL;

CREATE OR REPLACE VIEW vw_data_quality_summary AS
SELECT check_id, table_name, COUNT(*) AS failure_count
FROM vw_data_quality_findings
GROUP BY check_id, table_name;
