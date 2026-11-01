# Resume and profile text

Use these only with the seed-42 figures measured in `reports/evaluation_report.md`, `reports/run_summary.json`, and `reports/data_quality_report.md`. They describe a synthetic screening project. They are not operational accuracy, time saved, or money recovered.

## Resume bullets

- Built ProcureGuard, a synthetic procurement-screening workflow in Python, PostgreSQL, and Power BI: 120 employees, 60 vendors, 850 purchase orders, 1,500 invoices, 1,400 payments, and 900 expense claims, with planted suspicious cases and benign controls.
- Wrote 17 explainable rules and a weighted 0–100 vendor risk score; the seed-42 run produced 230 pending-review alerts and scored every vendor Low (52) or Medium (8), with a top score of 34.38.
- Evaluated each rule against held-out synthetic labels: unweighted mean F1 0.9584, including designed misses (near-time recall 0.7143) and designed false positives (early-payment precision 0.6250, late-payment precision 0.7143, off-hours precision 0.7500). Data-quality pass rate on 30 checks was 50%.

## Technical skills line

SQL, PostgreSQL, Python, Pandas, data quality, financial reconciliation, Benford's Law, anomaly screening, vendor risk scoring, Power BI, DAX.

## GitHub repository description

Synthetic procurement fraud-screening and vendor-risk project: PostgreSQL, Python, explainable rules, and a Power BI import model. Alerts are pending review, not confirmed fraud.

## LinkedIn project description

ProcureGuard is a portfolio analytics project that generates a synthetic INR procurement book, checks data quality, loads PostgreSQL, and screens invoices, purchase orders, payments, and expenses with documented rules. Vendor risk is a weighted 0–100 score with the contribution of each factor shown. On the published seed the screen raised 230 alerts for review, the highest vendor score was Medium at 34.38, and rule-level precision and recall were calculated against planted labels, including benign controls. A deviation from Benford's Law is reported as a digit test, not as proof of fraud. The Power BI layer is specified as an Import-mode model with DAX measures; the repository does not ship a PBIX file.
