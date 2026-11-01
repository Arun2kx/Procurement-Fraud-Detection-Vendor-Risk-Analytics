# Data quality report

This report describes the synthetic raw files. Failed checks are retained in those files.
Rows rejected later by a PostgreSQL constraint are listed in the ingestion rejection log and are not silently deleted here.

- Checks executed: 30
- Checks passed: 15
- Check pass rate: 50.00%
- Failed-record rows: 69

## Failed checks

- INVOICE_MATH_MISMATCH on invoices: 13 rows
- NEGATIVE_AMOUNT on invoices: 12 rows
- ORPHAN_PO_REFERENCE on invoices: 6 rows
- OUT_OF_RANGE_DATE on employee_expenses: 6 rows
- INVALID_DATE_SEQUENCE on invoices: 4 rows
- INVALID_CATEGORY on invoices: 4 rows
- DUPLICATE_BANK_HASH on vendors: 4 rows
- NULL_EMPLOYEE_EMAIL on employees: 4 rows
- NULL_VENDOR_CITY on vendors: 3 rows
- ORPHAN_INVOICE_REFERENCE on payments: 3 rows
- NEGATIVE_AMOUNT on employee_expenses: 3 rows
- TRANSACTION_BEFORE_HIRE on employee_expenses: 3 rows
- DUPLICATE_PRIMARY_KEY on invoices: 2 rows
- INVALID_CATEGORY on vendors: 1 rows
- INVALID_CATEGORY on employees: 1 rows

A failed check is a data defect or a referential break. It is not, by itself, a fraud finding.
