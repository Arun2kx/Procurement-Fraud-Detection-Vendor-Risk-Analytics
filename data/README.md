# Dataset documentation

Every file under `data/` is synthetic. Names, GSTINs, bank-account hashes, and amounts were generated for this portfolio project. They are not customers, vendors, employees, or losses from any organisation. GSTIN values use the fictional state code `99` and are not valid registration numbers. Bank hashes are SHA-256 digests of synthetic tokens, not real account numbers.

Currency is INR. The study window is 1 April 2023 through 31 March 2025. The generator seed is 42.

## Files

| Path | Role |
| --- | --- |
| `data/raw/*.csv` | Operational inputs. Detection reads these files. |
| `data/raw/generation_manifest.json` | Seed, row counts, and generation timestamp. |
| `data/evaluation/ground_truth_labels.csv` | Planted labels. The evaluation module reads this after detection. Detection and scoring code do not. |
| `data/processed/` | Quality results, alerts, scores, reconciliation, and statistics written by `python -m src.pipeline analyze`. |
| `data/processed/powerbi/` | Star-schema extracts for Power BI Import mode. |
| `data/processed/ingestion_rejections.csv` | Rows PostgreSQL refused. Present after a successful `ingest` run. |

## Operational tables

Row counts for seed 42: employees 120, vendors 60, purchase orders 850, invoices 1,500, payments 1,400, employee expenses 900, approval records 1,785. Ground-truth labels: 765.

### employees.csv

| Column | Description |
| --- | --- |
| employee_id | Primary key, `EMP###`. |
| full_name | Synthetic name. |
| email | Synthetic `@procureguard.example` address. A few rows are blank on purpose. |
| department | One of eight departments. |
| job_title, job_level | Director, Department Head, Manager, Senior Analyst, or Analyst. |
| manager_id | Another employee, or blank for the director. |
| approval_limit_inr | 50,000 / 200,000 / 500,000 / 2,000,000 by level. |
| hire_date | Between 2014 and 2022. |
| employment_status | Active or Inactive in valid rows. One planted row uses `On Leave`. |
| city | Indian city from the generator catalog. |

### vendors.csv

| Column | Description |
| --- | --- |
| vendor_id | Primary key, `VEN###`. |
| vendor_name | Synthetic company name. |
| vendor_category | Eight procurement categories. |
| gstin | Synthetic, not a valid GSTIN. |
| city, state | City may be blank on planted defect rows. |
| bank_account_hash | SHA-256 of a synthetic token. Two pairs share a hash. |
| onboarding_date | Vendor start date. |
| vendor_status | Active, Suspended, or Inactive. One planted row is `UNKNOWN`. |
| contact_email | Synthetic `@vendors.example` address. |
| payment_terms_days | Integer days. |

### purchase_orders.csv

| Column | Description |
| --- | --- |
| po_id | Primary key, `PO######`. |
| vendor_id, requestor_employee_id | Foreign keys. |
| department, category | Department of the request and vendor category of the order. |
| po_date, po_amount_inr | Order date and amount. Amounts are positive. |
| currency | `INR`. |
| status | Approved, Closed, Pending, or Rejected. |
| description | Synthetic line description. |

### invoices.csv

| Column | Description |
| --- | --- |
| invoice_id | Primary key, `INV######`. Two planted rows repeat an existing key. |
| invoice_number | Vendor document number. |
| vendor_id, po_id | `po_id` may be blank for non-PO invoices. A few rows point at `PO-ORPHAN`. |
| invoice_date, due_date, submitted_at | A few due dates precede the invoice date. A few dates fall outside the study window. |
| item_code, item_description, quantity, unit_price_inr | Line identity and price. |
| invoice_amount_inr, tax_amount_inr, total_amount_inr | GST-inclusive totals at 18% for valid rows. Planted math defects break the identity. |
| currency | `INR`. |
| status | Submitted, Approved, Paid, Disputed, or Rejected. A few rows are `UNKNOWN`. |
| dispute_flag | Boolean. |
| description | Synthetic text. |

### payments.csv

| Column | Description |
| --- | --- |
| payment_id | Primary key, `PAY######`. |
| invoice_id, vendor_id | A few invoice ids are `INV-ORPHAN`. |
| payment_date, payment_amount_inr | Amounts are positive. |
| currency | `INR`. |
| payment_method | NEFT, RTGS, IMPS, or Cheque. |
| payment_reference | Synthetic reference. |
| status | Completed, Reversed, or Failed. |

### employee_expenses.csv

| Column | Description |
| --- | --- |
| expense_id | Primary key, `EXP######`. |
| employee_id | Claimant. |
| expense_date, submitted_at | A few dates fall outside the window or before hire. |
| category | Meals, Fuel, Travel, Lodging, Client Entertainment, or Office Supplies. |
| amount_inr | A few planted rows are negative. |
| currency | `INR`. |
| description | Synthetic text. |
| receipt_attached | Boolean. |
| status | Submitted, Approved, Reimbursed, or Rejected. |

### approval_records.csv

| Column | Description |
| --- | --- |
| approval_id | Primary key, `APR######`. |
| entity_type | `purchase_order`, `invoice`, or `employee_expense`. |
| entity_id | Identifier in the corresponding table. There is no single foreign key; the quality views check the reference. |
| approver_employee_id | Approver. |
| approval_date, decision | Approved, Rejected, or Returned. |
| approval_level | Job level of the approver. |
| comments | Synthetic text. |

## Ground truth

`ground_truth_labels.csv` is evaluation-only.

| Column | Description |
| --- | --- |
| label_id | `LBL######`. |
| entity_type, entity_id | Grain of the label. |
| pattern_code | Planted pattern name. |
| is_suspicious | Positive class for a matching detection rule. |
| is_benign_control | Lookalike that the rule should leave alone, or a control the rule is expected to flag when the rule cannot see the context. |
| is_data_quality_defect | Defect label. These are not fraud positives. |
| pattern_description | Short explanation of the plant. |
| related_entity_ids | Other ids in the same planted group. |

Suspicious patterns include exact, near-time, and fuzzy invoice duplicates; split purchases; threshold gaming; duplicate, early, late, and mismatched payments; duplicate and off-hours expenses; self-approval; purchase-order approval gaps; price volatility; and high dispute rates.

Benign controls include recurring monthly invoices, repeated amounts, high-volume vendors, progress bills, valid splits approved within the director limit, one-off near-threshold orders, partial payments, one-day posting lags, seasonal price variation, and ordinary off-hours claims that carry a receipt or a small amount.

## What the generator is designed to hide

Near-time duplicates that use the next serial invoice number sit inside the sequential-number exclusion and are false negatives for that rule. Posting lags, ordinary late payments, and weekend claims that look like the off-hours rule are false positives. A valid three-way split approved by a director stays in the cluster view with disposition `adequate_approval` and does not become an alert.
