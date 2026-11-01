"""Create the read-only pipeline review notebook."""

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

HERE = Path(__file__).resolve().parent

cells = [
    new_markdown_cell(
        "# ProcureGuard pipeline review\n\n"
        "This notebook only reads files the analysis pipeline has already written. "
        "It does not detect fraud again and it does not change a score. "
        "Every record is synthetic. Every alert is Pending Review until a person changes that status. "
        "There is no web application and no Power BI PBIX file in this project."
    ),
    new_code_cell(
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "import pandas as pd\n"
        "from IPython.display import Image, display\n\n"
        "root = Path.cwd().resolve()\n"
        "if root.name == 'notebooks':\n"
        "    root = root.parent\n"
        "sys.path.insert(0, str(root))\n"
        "pd.set_option('display.max_columns', 12)\n"
        "pd.set_option('display.width', 140)\n"
        "pd.set_option('display.max_colwidth', 88)\n"
        "summary = json.loads((root / 'reports' / 'run_summary.json').read_text(encoding='utf-8'))\n"
        "alerts = pd.read_csv(root / 'data' / 'processed' / 'audit_alerts.csv')\n"
        "scores = pd.read_csv(root / 'data' / 'processed' / 'vendor_risk_scores.csv')\n"
        "invoices = pd.read_csv(root / 'data' / 'raw' / 'invoices.csv')\n"
        "checks = pd.read_csv(root / 'data' / 'processed' / 'data_quality_checks.csv')\n"
        "failures = pd.read_csv(root / 'data' / 'processed' / 'data_quality_failures.csv')\n"
        "metrics = pd.read_csv(root / 'data' / 'evaluation' / 'rule_metrics.csv')\n"
        "print('generated_at', summary['generated_at'])\n"
        "print('alerts', int(summary['alerts']), 'vendors_scored', int(summary['vendors_scored']))"
    ),
    new_markdown_cell("## Executive overview\n\n<a id=\"executive-overview\"></a>\n\nCounts and exposure come from the latest `analyze` run. Positive invoice totals are summed from the raw synthetic file."),
    new_code_cell(
        "positive = pd.to_numeric(invoices['total_amount_inr'], errors='coerce')\n"
        "spend = float(positive[positive > 0].sum())\n"
        "overview = pd.DataFrame([\n"
        "    ['Invoices in the raw file', int(len(invoices))],\n"
        "    ['Positive procurement spend (INR)', round(spend, 2)],\n"
        "    ['Alerts', int(summary['alerts'])],\n"
        "    ['Alerts pending review', int((alerts['review_status'] == 'Pending Review').sum())],\n"
        "    ['Potential exposure (INR)', float(summary['potential_exposure_inr'])],\n"
        "    ['Vendors scored', int(summary['vendors_scored'])],\n"
        "    ['High or critical vendors', int(summary['high_or_critical_vendors'])],\n"
        "    ['Data-quality pass rate', float(summary['data_quality_pass_rate'])],\n"
        "], columns=['measure', 'value'])\n"
        "display(overview)\n"
        "display(scores['risk_category'].value_counts().rename_axis('risk_category').reset_index(name='vendors'))\n"
        "display(Image(filename=str(root / 'screenshots' / '01_monthly_spend.png')))\n"
        "display(Image(filename=str(root / 'screenshots' / '03_vendor_risk_distribution.png')))"
    ),
    new_markdown_cell("## Fraud alerts\n\n<a id=\"fraud-alerts\"></a>\n\nInvoice-level alerts from `audit_alerts.csv`. Exposure on the anchor copy of a duplicate pair is zero so the pair is not added twice. Review status is still Pending Review."),
    new_code_cell(
        "totals = invoices[['invoice_id', 'total_amount_inr']].copy()\n"
        "totals['total_amount_inr'] = pd.to_numeric(totals['total_amount_inr'], errors='coerce')\n"
        "invoice_alerts = alerts[alerts['entity_type'] == 'invoice'].merge(\n"
        "    totals, left_on='entity_id', right_on='invoice_id', how='left'\n"
        ")\n"
        "columns = ['alert_id', 'rule_name', 'entity_id', 'vendor_id', 'total_amount_inr', 'estimated_exposure_inr', 'severity', 'review_status']\n"
        "display(invoice_alerts[columns].head(12))\n"
        "print('invoice_alerts', len(invoice_alerts), 'of', len(alerts), 'alerts')"
    ),
    new_markdown_cell("## Vendor risk\n\n<a id=\"vendor-risk\"></a>\n\nThe 0–100 score and category are the pipeline output. Factor columns are the observed rates, not the weighted points."),
    new_code_cell(
        "risk_columns = [\n"
        "    'vendor_id', 'vendor_name', 'vendor_category', 'risk_score', 'risk_category',\n"
        "    'raw_duplicate_invoice_rate', 'raw_dispute_rate', 'raw_price_volatility',\n"
        "    'raw_split_purchase_involvement', 'raw_po_approval_violations', 'raw_payment_anomaly_rate',\n"
        "]\n"
        "display(scores.sort_values('risk_score', ascending=False)[risk_columns].head(10))\n"
        "print('highest_score', float(scores['risk_score'].max()))\n"
        "print(scores['risk_category'].value_counts().to_string())"
    ),
    new_markdown_cell("## Data quality\n\n<a id=\"data-quality\"></a>\n\nA failed check stays in the raw file. It is a defect, not a fraud finding."),
    new_code_cell(
        "print('checks', len(checks), 'passed', int(checks['passed'].sum()), 'failed', int((~checks['passed']).sum()))\n"
        "print('pass_rate', round(float(checks['passed'].mean()), 4))\n"
        "display(checks.sort_values(['passed', 'check_id']))\n"
        "reasons = (\n"
        "    failures.groupby(['check_id', 'table_name', 'reason'], as_index=False)\n"
        "    .size()\n"
        "    .rename(columns={'size': 'failed_rows'})\n"
        "    .sort_values('failed_rows', ascending=False)\n"
        ")\n"
        "display(reasons)"
    ),
    new_markdown_cell("## Fraud-detection results\n\n<a id=\"fraud-detection\"></a>\n\nRule metrics compare alerts with planted synthetic labels. The Benford chart is the invoice screen from the same run. A digit deviation is not evidence of fraud."),
    new_code_cell(
        "metric_columns = ['rule_code', 'positives', 'predicted', 'true_positives', 'false_positives', 'false_negatives', 'precision', 'recall', 'f1_score', 'benign_controls_flagged']\n"
        "display(metrics[metric_columns])\n"
        "print('unweighted_mean_f1', round(float(metrics['f1_score'].mean()), 4))\n"
        "print('invoice_benford_n', summary['benford_invoice_sample_size'])\n"
        "print('invoice_benford_mad', summary['benford_invoice_mad'])\n"
        "print('invoice_benford_p_value', summary['benford_invoice_p_value'])\n"
        "print('invoice_benford_band', summary['benford_invoice_band'])\n"
        "display(Image(filename=str(root / 'screenshots' / '05_benford_invoices.png')))"
    ),
    new_markdown_cell("## Invoice investigation\n\n<a id=\"invoice-investigation\"></a>\n\nOne flagged invoice alert and the invoice rows named in its stored evidence. The evidence text is the JSON written by the detector."),
    new_code_cell(
        "flagged = alerts[(alerts['entity_type'] == 'invoice') & (alerts['estimated_exposure_inr'] > 0)].sort_values('alert_id').iloc[0]\n"
        "evidence = json.loads(flagged['supporting_evidence'])\n"
        "display(flagged[['alert_id', 'rule_name', 'entity_id', 'vendor_id', 'severity', 'estimated_exposure_inr', 'detection_reason', 'review_status']].to_frame().T)\n"
        "print(flagged['supporting_evidence'])\n"
        "related = invoices[invoices['invoice_id'].isin(evidence['invoice_ids'])][\n"
        "    ['invoice_id', 'invoice_number', 'vendor_id', 'invoice_date', 'total_amount_inr', 'status', 'dispute_flag']\n"
        "]\n"
        "display(related)"
    ),
]

book = new_notebook(cells=cells)
book.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
book.metadata["language_info"] = {"name": "python", "pygments_lexer": "ipython3"}
nbformat.write(book, HERE / "03_pipeline_review.ipynb")
