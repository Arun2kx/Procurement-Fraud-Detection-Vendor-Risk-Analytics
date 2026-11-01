# Power BI build guide

Power BI Desktop is the presentation layer. This repository does not contain a PBIX or PBIT file. Those binaries are gitignored. The files below were produced by the Python pipeline and checked as CSV extracts. They were not opened in Power BI Desktop during the build, so this guide is the implementation specification rather than a claim that a dashboard file was generated or refreshed.

## Connection

1. Install Power BI Desktop.
2. Get data, Text/CSV, and select every file in `data/processed/powerbi`, or use Folder and combine after giving each file its own query.
3. Use **Import** mode. The extracts are small, the measures are row-context calculations over a static study window, and Import keeps the dashboard usable without a live database.
4. Set the date column types before loading: `dim_date[date]`, `fact_invoice[invoice_date]`, `fact_invoice[due_date]`, `fact_payment[payment_date]`, `fact_purchase_order[po_date]`, `fact_expense[expense_date]`.
5. After `python -m src.pipeline analyze`, refresh the PBIX. Do not point the model at `data/evaluation/ground_truth_labels.csv`.

A DirectQuery model against the PostgreSQL views is possible later. The verified path is Import, because the Python extracts and the SQL views do not match row for row (see `reports/postgres_verification.md`).

## Theme

- Background `#F7F4EF`
- Navy `#0B1F3A` for titles, axes, and the header bar
- Gold `#C4A35A` for the primary data colour and KPI accent
- Slate `#4E5D6C` for secondary text
- Alert severity: Critical `#7A1F2B`, High `#B4532A`, Medium `#C4A35A`, Low `#3D6B58`
- Segoe UI, or the closest available sans-serif
- Card padding 12 px, visual gap 16 px, page margin 24 px
- No decorative icons, no background photographs, no 3-D charts

Page header text: `ProcureGuard — synthetic procurement screening`. Footer: `Alerts are pending review. Figures are not confirmed fraud or real losses.`

## Data model

Mark `dim_date` as a date table on `date`. The fiscal year starts in April. `fiscal_year_label` looks like `FY2023-24`.

| From | To | Cardinality | Active |
| --- | --- | --- | --- |
| dim_vendor[vendor_id] | fact_invoice[vendor_id] | one to many | yes |
| dim_vendor[vendor_id] | fact_payment[vendor_id] | one to many | yes |
| dim_vendor[vendor_id] | fact_purchase_order[vendor_id] | one to many | yes |
| dim_vendor[vendor_id] | fact_alert[vendor_id] | one to many | yes |
| dim_vendor[vendor_id] | fact_vendor_risk[vendor_id] | one to one | yes |
| dim_vendor[vendor_id] | fact_reconciliation[vendor_id] | one to many | yes |
| dim_employee[employee_id] | fact_expense[employee_id] | one to many | yes |
| dim_employee[employee_id] | fact_purchase_order[requestor_employee_id] | one to many | yes |
| dim_employee[employee_id] | fact_approval[approver_employee_id] | one to many | yes |
| dim_employee[employee_id] | fact_alert[employee_id] | one to many | yes |
| dim_date[date] | fact_invoice[invoice_date] | one to many | yes |
| dim_date[date] | fact_invoice[due_date] | one to many | no |
| dim_date[date] | fact_payment[payment_date] | one to many | yes |
| dim_date[date] | fact_purchase_order[po_date] | one to many | yes |
| dim_date[date] | fact_expense[expense_date] | one to many | yes |

`fact_benford`, `fact_rule_performance`, and `fact_data_quality` stay disconnected. They are page-level tables, not facts sliced by vendor. Blank `vendor_id` or `employee_id` values on alerts are employee-only or vendor-only screens and will not match a dimension row. That is expected.

Create the measures in `dax_measures_reference.md`.

## Slicers, on every page except the disconnected governance charts

- `dim_date[fiscal_year_label]`
- `dim_vendor[vendor_category]`
- `fact_purchase_order[department]`
- `fact_vendor_risk[risk_category]`
- `fact_alert[review_status]`

Sync the fiscal year, category, and department slicers. Do not sync `rule_code`, because page 3 needs its own rule slicer.

## Drill-through

Add a drill-through filter on page 2 for `dim_vendor[vendor_id]`. Enable drill-through from the page 1 scatter (`spend_inr` against `risk_score`) and from the vendor ranking table. The destination shows that vendor's factor points, alerts, and invoices. Keep `Keep all filters` off so a category slicer does not hide the vendor's other categories by accident. Right-click a vendor point, Drill through, Vendor risk.

## Page 1 — Executive risk overview

KPI cards: Total Procurement Spend, Total Invoices, Total Alerts, Potential Exposure, High or Critical Vendors.

- Line chart: `dim_date[year_month]` and Total Procurement Spend.
- Donut: `fact_vendor_risk[risk_category]` and the vendor count.
- Scatter: vendor spend against risk score, colour by category. This is the drill-through source.
- Bar: `fact_alert[rule_code]` and Total Alerts.

The High or Critical card is 0 on the published seed. Keep it. Hiding a zero would make the scale look calibrated when it is not.

## Page 2 — Vendor risk analysis

- Table: vendor name, risk score, risk category, dispute rate, price-volatility points, duplicate-invoice points, spend share. Sort by risk score descending.
- Clustered bar of the seven `points_*` columns for the selected vendor. These columns are the weighted contributions and they sum to the score.
- Pareto line: `fact_vendor_risk[spend_inr]` sorted descending with a cumulative spend-share line. The 80% line is a reference, not a risk threshold.
- Column chart of category HHI is not in the star schema as its own fact. Use `data/processed/category_hhi.csv` as an additional imported table, `fact_category_hhi`, disconnected, with `hhi_points` by `vendor_category`.

## Page 3 — Fraud investigation

- Tables filtered to `EXACT_DUP_INVOICE`, `FUZZY_DUP_INVOICE`, and `NEAR_TIME_DUP_INVOICE`. Show entity id, vendor, severity, exposure, and detection reason.
- Matrix of `SPLIT_PURCHASE` and `THRESHOLD_GAMING` alerts.
- Table of `DUPLICATE_EXPENSE`, `THRESHOLD_GAMING_EXPENSE`, `OFFHOURS_EXPENSE`, and `SELF_APPROVAL`.
- Combo chart from `fact_benford`: observed share against expected share by digit, for the invoice population only. Title the visual with the sample size, MAD, and the sentence "A digit deviation is not evidence of fraud."

## Page 4 — Financial reconciliation

- Stacked bar of `fact_reconciliation[match_status]` for `record_type = purchase_order`.
- Table of rows whose status is `Invoiced and unpaid`, `Overpaid`, `Underpaid`, `Orphan purchase-order reference`, or `Paid above invoice`.
- Column of payment amount by month using `Payments on Payment Date`.
- Bar of purchase-order amount by department.
- Import `data/processed/department_monthly_spend.csv` if a department-month matrix is easier than reconstructing it from the facts.

Duplicate-payment and delay alerts stay on this page as a table filtered to `DUP_PAYMENT`, `EARLY_PAYMENT`, `LATE_PAYMENT`, and `PAYMENT_MISMATCH`.

## Page 5 — Data quality and audit governance

- Card: Data Quality Pass Rate. The verified seed-42 value is 50% (15 of 30 checks).
- Table: `fact_data_quality` where `passed` is false, with `failure_count`.
- Stacked bar of `fact_alert[review_status]`. On a fresh run every alert is Pending Review. The other three statuses exist so a reviewer can update the CSV and refresh. The pipeline does not invent review outcomes.
- Table of `fact_rule_performance` with precision, recall, F1, false positives, false negatives, and benign controls flagged.
- Card: Macro F1, titled "Unweighted mean F1, synthetic labels".

## What a reviewer should see on the seed-42 extract

- 230 alerts.
- Potential exposure INR 1,47,95,731.20, which is the sum of `estimated_exposure_inr`. Duplicate pairs put the exposure on the non-anchor row so the pair is not added twice. This number is process exposure on synthetic alerts.
- 60 scored vendors in the Python extract: 52 Low, 8 Medium, 0 High, 0 Critical. Highest score 34.38.
- Benford invoice band `marginal_conformity` (n = 875, MAD = 0.014080). Expense band `nonconformity`, which is the expected shape of policy-capped claims.
