# PostgreSQL verification

This note records one load of the seed-42 synthetic files into PostgreSQL 18.3. The cluster was created with `initdb` under the user temporary directory, listened on port 54329, used trust authentication for that local cluster only, and was stopped and deleted after the queries below. The existing PostgreSQL service and its authentication file were not changed. No password was written into the repository.

Python remains the evaluation source of truth. The SQL views are the analyst-facing equivalent and are expected to differ where the grain or the loaded population differs.

## Ingestion

The loader inserts each table in one transaction and rolls back only the savepoint of a rejected row. Raw rows equal loaded rows plus rejected rows.

| Table | Raw rows | Loaded | Rejected | Constraint that rejected the row |
| --- | ---: | ---: | ---: | --- |
| employees | 120 | 119 | 1 | `employees_employment_status_check` (`On Leave` is outside Active/Inactive) |
| vendors | 60 | 59 | 1 | `vendors_vendor_status_check` (`UNKNOWN`) |
| purchase_orders | 850 | 850 | 0 | — |
| invoices | 1,500 | 1,488 | 12 | 6 missing purchase orders, 4 `UNKNOWN` statuses, 2 duplicate primary keys |
| payments | 1,400 | 1,391 | 9 | invoice foreign key; the invoice was either absent or rejected above |
| employee_expenses | 900 | 900 | 0 | — |
| approval_records | 1,785 | 1,785 | 0 | — |
| audit_alerts_log | 230 | 230 | 0 | loaded from `data/processed/audit_alerts.csv` |

Rejected rows remain in `data/raw` and are listed in `data/processed/ingestion_rejections.csv`.

## View counts compared with the Python alert log

| Screen | Python alerts | SQL result |
| --- | ---: | --- |
| Exact duplicate invoices | 16 | 16 invoice rows |
| Fuzzy duplicate invoices | 16 | 8 pairs |
| Near-time duplicate invoices | 20 | 10 pairs |
| Split purchases, insufficient approval | 21 | 21 |
| Split purchases, adequate approval | 12 purchase orders kept out of the alert log | 12 |
| Threshold-gaming purchase orders | 12 | 12 |
| Duplicate expenses | 16 | 8 pairs |
| Threshold-gaming expenses | 20 | 20 |
| Off-hours expenses | 16 | 16 |
| Self-approvals | 14 | 14 |
| Duplicate payments | 20 | 20 |
| Early payments | 8 | 8 |
| Late payments | 21 | 21 |
| Payment amount mismatches | 5 | 5 |

## Differences that the comparison is meant to show

- `vw_benford_invoice_summary` used the loaded invoices: sample size 872, MAD 0.013863, chi-square statistic 26.3602, band `marginal_conformity`. The Python screen used the raw file after dropping duplicate keys: sample size 875, MAD 0.014080, p-value 0.000720, same conformity band. The chi-square p-value is computed in Python.
- `vw_vendor_risk_score` scored 59 vendors because the invalid-status vendor was rejected. The highest SQL score was 34.70. Python scored all 60 raw vendors; the highest score was 34.38 (VEN044, Medium). The SQL payment-anomaly factor counts timing exceptions. The Python factor also counts duplicate payments and amount mismatches, so the two scores are not required to match vendor by vendor.
- SQL risk categories on the loaded vendors were Low 53 and Medium 6. Python categories on the raw file were Low 52 and Medium 8. Neither run produced a High or Critical vendor.
- `vw_data_quality_findings` sees rows that loaded. It therefore reports the math mismatches, nulls, duplicate bank hashes, negative amounts, bad due dates, and expenses before hire. Orphan keys, illegal statuses, and the duplicate invoice key appear in the rejection log instead, because those rows never entered the tables. The Python quality module reads the raw files and is the pass-rate source (15 of 30 checks passed, 50%).
