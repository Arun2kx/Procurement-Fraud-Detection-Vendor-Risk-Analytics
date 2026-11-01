# Synthetic data generation summary

All records described here are synthetic. Nothing in this file is a real fraud finding or a real financial loss.

- Random seed: 42
- Currency: INR

## Row counts

- employees: 120
- vendors: 60
- purchase_orders: 850
- invoices: 1500
- payments: 1400
- employee_expenses: 900
- approval_records: 1785

## Planted pattern labels

- BENIGN_HIGH_VOLUME: 6 labels (benign control)
- BENIGN_LATE_PAYMENT: 6 labels (benign control)
- BENIGN_NEAR_THRESHOLD: 10 labels (benign control)
- BENIGN_NEAR_THRESHOLD_EXPENSE: 8 labels (benign control)
- BENIGN_NON_PO: 24 labels (benign control)
- BENIGN_OFFHOURS_CONTEXT: 4 labels (benign control)
- BENIGN_OFFHOURS_WITH_RECEIPT: 5 labels (benign control)
- BENIGN_PARTIAL_PAYMENT: 16 labels (benign control)
- BENIGN_POSTING_LAG: 3 labels (benign control)
- BENIGN_PRICE_VARIATION: 1 labels (benign control)
- BENIGN_PROGRESS_BILLING: 204 labels (benign control)
- BENIGN_RECURRING: 120 labels (benign control)
- BENIGN_REPEATED_AMOUNT: 15 labels (benign control)
- BENIGN_REPEATED_EXPENSE: 6 labels (benign control)
- BENIGN_REPEAT_ORDER: 4 labels (benign control)
- BENIGN_SMALL_OFFHOURS: 4 labels (benign control)
- BENIGN_VALID_SPLIT: 12 labels (benign control)
- BENIGN_WEEKDAY_NO_RECEIPT: 5 labels (benign control)
- DUPLICATE_BANK_HASH: 4 labels (data-quality defect)
- DUPLICATE_EXPENSE: 16 labels (suspicious)
- DUPLICATE_PRIMARY_KEY: 2 labels (data-quality defect)
- DUP_PAYMENT: 20 labels (suspicious)
- EARLY_PAYMENT: 5 labels (suspicious)
- EXACT_DUP_INVOICE: 16 labels (suspicious)
- FUZZY_DUP_INVOICE: 16 labels (suspicious)
- HIGH_DISPUTE_RATE: 4 labels (suspicious)
- INVALID_CATEGORY: 6 labels (data-quality defect)
- INVALID_DATE_SEQUENCE: 4 labels (data-quality defect)
- INVOICE_MATH_MISMATCH: 5 labels (data-quality defect)
- INVOICE_PO_MISMATCH: 8 labels (data-quality defect)
- LATE_PAYMENT: 15 labels (suspicious)
- NEAR_TIME_DUP_INVOICE: 28 labels (suspicious)
- NEGATIVE_AMOUNT: 6 labels (data-quality defect)
- NULL_EMAIL: 4 labels (data-quality defect)
- NULL_VENDOR_CITY: 3 labels (data-quality defect)
- OFFHOURS_EXPENSE: 12 labels (suspicious)
- ORPHAN_INVOICE_REFERENCE: 3 labels (data-quality defect)
- ORPHAN_PO_REFERENCE: 6 labels (data-quality defect)
- OUT_OF_RANGE_DATE: 3 labels (data-quality defect)
- PAYMENT_MISMATCH: 5 labels (suspicious)
- PO_APPROVAL_LIMIT_BREACH: 8 labels (suspicious)
- PO_MISSING_APPROVAL: 10 labels (suspicious)
- PRICE_VOLATILITY: 33 labels (suspicious)
- SELF_APPROVAL: 14 labels (suspicious)
- SPLIT_PURCHASE: 21 labels (suspicious)
- THRESHOLD_GAMING: 12 labels (suspicious)
- THRESHOLD_GAMING_EXPENSE: 20 labels (suspicious)
- TRANSACTION_BEFORE_HIRE: 3 labels (data-quality defect)

All people, vendors, GSTINs, bank hashes, and transactions are synthetic. They are not real fraud cases or real financial losses.
