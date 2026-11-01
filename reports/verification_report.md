# Verification review

Reviewed on 1 November 2026 against the seed-42 files produced by `python -m src.pipeline analyze` at 2026-10-31 16:38:20.

This review re-read the raw CSVs, re-ran the 30 data-quality checks, re-ran the 17 detection rules, re-scored all 60 vendors, re-executed the three notebooks on a clean kernel, and re-ran pytest. Detection code and the dataset were not changed to improve the figures.

All people, vendors, and amounts are synthetic. The exposure below is a screening total on synthetic alerts. It is not a government loss, not money recovered, and not confirmed fraud. Every stored alert has review status `Pending Review`.

There is no web application and no Power BI PBIX file. The review interface is the Jupyter notebook `notebooks/03_pipeline_review.ipynb`.

## 1. Dataset

| Table | Rows counted from `data/raw` |
| --- | ---: |
| employees | 120 |
| vendors | 60 |
| purchase_orders | 850 |
| invoices | 1,500 |
| payments | 1,400 |
| employee_expenses | 900 |
| approval_records | 1,785 |

The four counts requested for this review match the files: 60 vendors, 850 purchase orders, 1,500 invoices, 1,400 payments.

Missing values in the raw files:

| Table | Column | Missing rows |
| --- | --- | ---: |
| employees | email | 4 |
| vendors | city | 3 |

Other operational columns in those seven files had no nulls in this read.

Other defects found in the same files:

| Check | Count |
| --- | ---: |
| Extra duplicate invoice primary-key rows | 2 |
| Invoice rows whose purchase-order id is not in `purchase_orders.csv` | 6 |
| Payment rows whose invoice id is not in `invoices.csv` | 3 |
| Invoice rows whose taxable amount plus tax differs from the total by more than INR 0.05 | 13 |
| Invoice rows with a negative total | 3 |
| Invoices pointing at an unknown vendor | 0 |
| Purchase orders pointing at an unknown requestor | 0 |

Positive invoice totals sum to INR 6,59,51,747.62. That is the synthetic procurement spend in the raw file. It is a different number from the alert exposure.

## 2. Data-quality checks

`validate_tables` was run again on the raw files.

| Result | Count |
| --- | ---: |
| Checks executed | 30 |
| Passed | 15 |
| Failed | 15 |
| Skipped | 0 |
| Failed-record rows | 69 |
| Pass rate | 50% |

The 15 failed checks, from `reports/data_quality_report.md` written by the same pipeline, are:

- Invoice math mismatch, 13 rows
- Negative invoice amounts, 12 column-level rows (3 invoices across the amount columns)
- Orphan purchase-order references, 6
- Expense dates outside the study window, 6
- Due date before invoice date, 4
- Illegal invoice status, 4
- Shared vendor bank-account hash, 4
- Missing employee email, 4
- Missing vendor city, 3
- Orphan invoice references on payments, 3
- Negative expense amounts, 3
- Expense before hire, 3
- Duplicate invoice primary key, 2
- Illegal vendor status, 1
- Illegal employee status, 1

These failed checks are planted defects retained in the raw files. They were not marked as passed.

## 3. Fraud detection

Detection is rule-based. Isolation Forest is fit as a comparison column on the vendor-score file and is not the fraud detector. Six vendors carry that comparison flag. It is not added to the 0–100 score and it is not one of the 17 rules.

The detector does not read `data/evaluation/ground_truth_labels.csv`. That separation is also covered by `test_detection_modules_do_not_read_ground_truth`. Re-running `detect_patterns` on the raw files reproduced the stored alert log exactly: 230 alerts, the same `(rule_code, entity_id)` pairs, and the same exposure total.

The synthetic generator plants the patterns these rules look for, and it also plants benign lookalikes. An alert is a match to a coded condition on that synthetic book. It is not a label copied out of the ground-truth file, and it is not a confirmed case.

| Rule | Alerts | Condition used by the code | Sample record |
| --- | ---: | --- | --- |
| EXACT_DUP_INVOICE | 16 | Same vendor and invoice number, case-insensitive | ALT000059, INV000240, VEN052. Raw check: INV000240 and INV000241 are both `SA2-2023-10001`, vendor VEN052, total INR 49,560.00 |
| NEAR_TIME_DUP_INVOICE | 20 | Same vendor and item, amount within 1%, dates within 5 days, invoice numbers not an exact, fuzzy, or near-serial match. Recurring `-REC` items are excluded | ALT000160, INV000256, VEN031 |
| FUZZY_DUP_INVOICE | 16 | Same normalised number with different punctuation, or Levenshtein distance 1, excluding a trailing-number gap of 80 or less | ALT000075, INV000288, VEN037 |
| SPLIT_PURCHASE | 21 | Same vendor, department, and category; each order under INR 2,00,000; dates within 14 days; combined value at least INR 2,00,000; highest approver limit below the combined value | ALT000114, PO000160, VEN012, exposure INR 5,16,000.00 |
| THRESHOLD_GAMING | 12 | At least 3 orders for one vendor in [INR 1,80,000, INR 2,00,000) inside 90 days | ALT000183, PO000193, VEN023 |
| DUP_PAYMENT | 20 | At least two completed payments each covering at least 98% of the invoice total | ALT000001, PAY000001, VEN008 |
| EARLY_PAYMENT | 8 | Completed payment date before the invoice date | ALT000051, PAY000025, VEN011, exposure INR 10,137.14 |
| LATE_PAYMENT | 21 | Completed payment more than 60 days after the due date, and the invoice is not disputed | ALT000139, PAY000033, VEN050 |
| PAYMENT_MISMATCH | 5 | Completed payments differ from the invoice total by more than 2%, and the duplicate-payment rule has not already fired | ALT000091, PAY000061, VEN007, exposure INR 4,516.59 |
| DUPLICATE_EXPENSE | 16 | Same employee, category, and rounded amount, with expense dates at most one day apart | ALT000035, EXP000026 |
| THRESHOLD_GAMING_EXPENSE | 20 | At least 3 claims in the same employee and category inside 90% of the category cap, within 90 days | ALT000195, EXP000010, exposure INR 19,160.00 |
| OFFHOURS_EXPENSE | 16 | Amount at least INR 2,000, no receipt, weekend submission, and hour at or after 22:00 or before 06:00 | ALT000215, EXP000083, exposure INR 4,500.00 |
| SELF_APPROVAL | 14 | Approver is the purchase requestor or the expense claimant, and the decision is Approved | ALT000021, APR000215, exposure INR 94,999.99 |
| PO_APPROVAL_LIMIT_BREACH | 8 | Highest approval limit on an Approved decision is below the purchase-order amount | ALT000096, PO000231, VEN042, exposure INR 3,50,000.00 |
| PO_MISSING_APPROVAL | 10 | Approved or closed order of at least INR 50,000 with no approval row | ALT000104, PO000215, VEN037, exposure INR 80,000.00 |
| PRICE_VOLATILITY | 3 | Coefficient of variation of unit price at least 0.30 on one item with at least 6 observations | ALT000180, VEN027, item EQP-VOL-01, CV 0.38 |
| HIGH_DISPUTE_RATE | 4 | Dispute rate at least 15% and at least 5 disputed invoices | ALT000135, VEN031 |

Exposure on the first record of a duplicate group is stored as zero so the pair is not added twice. A zero on the sample row is that anchor convention, not a missing amount. The pair total for INV000240 / INV000241 is on ALT000060.

The published evaluation against planted labels is in `reports/evaluation_report.md`. Re-reading `data/evaluation/rule_metrics.csv` gives 17 rules and an unweighted mean F1 of 0.9584. That figure is a synthetic test summary. It is not an operational accuracy rate. The same file shows the designed errors: near-time recall 0.7143 (8 serial-number misses), early-payment precision 0.6250 (3 one-day posting lags), late-payment precision 0.7143 (6 benign late payments), and off-hours precision 0.7500 (4 lookalike weekend claims). Several structural rules score perfectly because the generator plants the pattern the rule is written to find.

## 4. Vendor risk score

Seven factors. Weights from `config/config.example.yaml` sum to 1.00.

| Factor | Weight | Raw input | Anchor that scores 100 on the factor |
| --- | ---: | --- | --- |
| Duplicate invoice rate | 0.22 | Duplicate-invoice alerts / invoices | 0.15 |
| Dispute rate | 0.10 | Disputed invoices / invoices | 0.20 |
| Price volatility | 0.12 | Maximum item CV | 0.50 |
| Split-purchase involvement | 0.18 | Insufficient-approval split orders / purchase orders | 0.25 |
| PO approval violations | 0.16 | Missing approval, limit breach, or self-approved orders / purchase orders | 0.10 |
| Payment anomaly rate | 0.14 | Duplicate, early, mismatch, or late payments / payments | 0.15 |
| Spend concentration | 0.08 | `(spend share − 0.05) / 0.20`, floored at 0 | scale anchor 1.0 |

Each factor score is `min(100, max(0, raw / anchor × 100))`. The vendor score is the weighted sum of those factor scores, rounded to 2 decimals. Categories: Low through 25, Medium through 50, High through 75, Critical above 75.

Re-scoring the 60 vendors from the recomputed alerts matched the stored file. The largest absolute score difference was 0.00, and no category changed.

Stored result: 52 Low, 8 Medium, 0 High, 0 Critical. Highest score 34.38. A single factor cannot contribute more than its weight times 100, so this scale does not produce a Critical vendor from one pattern. The weights are documented screening weights. They are not fitted to reviewed losses.

## 5. Alert count and exposure

| Measure | Stored file | Recomputed in this review |
| --- | ---: | ---: |
| Alerts | 230 | 230 |
| Alert pairs that differed | — | 0 |
| Sum of `estimated_exposure_inr` | INR 1,47,95,731.20 | INR 1,47,95,731.20 |
| Same sum in crore | 1.4796 | 1.4796 |
| Review status Pending Review | 230 | 230 |

INR 1,47,95,731.20 is about ₹1.48 crore. The exact recomputed sum is INR 1,47,95,731.20. It is the sum of the screening exposures written by the rules, with duplicate groups counted once. It is a synthetic-data result. It is not an actual government loss and not confirmed fraud.

## 6. Automated tests

`python -m pytest tests/test_procureguard.py` on Python 3.12.1, pytest 9.1.1:

| Result | Count |
| --- | ---: |
| Passed | 11 |
| Failed | 0 |
| Skipped | 0 |

The 11 tests are `test_invoice_number_helpers`, `test_risk_weights_sum_to_one`, `test_confusion_formula`, `test_benford_refuses_small_samples`, `test_sql_splitter_keeps_function_body_together`, `test_detection_modules_do_not_read_ground_truth`, `test_generation_shape_and_reproducibility`, `test_screening_against_planted_labels`, `test_handmade_duplicate_and_split_rules`, `test_quality_finds_planted_defects`, and `test_rule_catalog_covers_alert_codes`. Runtime was 22.66 seconds. Pytest’s quiet setting printed a dot per test; the session line was `11 passed`.

## 7. Notebook execution

All three notebooks were executed from a new kernel, in cell order, with the working directory set to the project root.

| Notebook | Cells | Error outputs |
| --- | ---: | ---: |
| `notebooks/01_exploratory_data_analysis.ipynb` | 10 | 0 |
| `notebooks/02_statistical_analysis.ipynb` | 9 | 0 |
| `notebooks/03_pipeline_review.ipynb` | 14 | 0 |

The source cells load the raw files, the processed alert and score files, or the project functions. The figures 230, INR 1,47,95,731.20, and mean F1 0.9584 appear as computed outputs, not as literals typed into the result cells. Charts displayed in the notebooks are the PNG files written by the analysis pipeline under `screenshots/`.

Rendered pages, including the tables and charts:

- `reports/notebook_exports/01_exploratory_data_analysis.html`
- `reports/notebook_exports/02_statistical_analysis.html`
- `reports/notebook_exports/03_pipeline_review.html`

Pipeline chart files, which the notebooks also display:

- `screenshots/01_monthly_spend.png`
- `screenshots/02_department_spend.png`
- `screenshots/03_vendor_risk_distribution.png`
- `screenshots/04_alerts_by_rule.png`
- `screenshots/05_benford_invoices.png`
- `screenshots/06_vendor_pareto.png`
- `screenshots/07_invoice_amount_distribution.png`

A browser screenshot of the live Jupyter window was not captured in this review. The previous browser capture did not return. The HTML pages above are the exported notebook outputs.

## 8. Implemented and incomplete

Implemented and checked in this review:

- Seeded synthetic procurement book and a separate ground-truth file
- 30 data-quality checks that keep failed rows
- 17 explainable detection rules
- Seven-factor vendor score with stored explanations
- Synthetic evaluation with precision, recall, and F1 by rule
- 11 pytest tests
- Three executed notebooks
- Matplotlib chart exports
- SQL scripts and a prior PostgreSQL 18.3 load recorded in `reports/postgres_verification.md`

Incomplete, or present only as a specification:

- No web application
- No Power BI PBIX. `dashboard/` contains DAX and build instructions for Import mode. Those pages were not opened in Power BI Desktop in this review
- No reviewer workflow. All 230 alerts remain Pending Review
- Isolation Forest is a comparison flag, not a fraud model
- Risk weights are not calibrated on closed investigations
- The PostgreSQL load was not repeated on 1 November 2026. The October 31 load note remains the database evidence
- Jupyter HTML exports are the review pages. They are not a deployed dashboard

## 9. Resume recommendation

This project is ready to show on a Data Analyst resume as a synthetic procurement-screening portfolio, with the measured scope stated plainly: 60 vendors, 850 purchase orders, 1,500 invoices, 1,400 payments, 17 rules, 230 pending-review alerts, a top vendor score of 34.38, a 50% data-quality pass rate, and an unweighted synthetic mean F1 of 0.9584.

It is not ready to be described as a deployed fraud product, a machine-learning detector, a live Power BI dashboard, or evidence of money recovered. The 0.9584 figure belongs next to the words “synthetic labels,” including the rules that miss serial-number duplicates and the rules that flag benign controls.
