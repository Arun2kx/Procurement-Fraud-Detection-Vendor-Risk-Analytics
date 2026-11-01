# DAX measure reference

These measures are written for the Import-mode tables in `data/processed/powerbi`. A PBIX file was not created or validated in Power BI Desktop. Paste the measures into the model after the relationships in `dashboard_build_guide.md` are in place.

Format currency measures as Indian rupees with two decimals. Format rates as percentages. `Potential Exposure` is the sum of screening exposures on synthetic alerts. It is not a loss.

```dax
Total Procurement Spend =
CALCULATE(
    SUM(fact_invoice[total_amount_inr]),
    fact_invoice[total_amount_inr] > 0
)
```

```dax
Total Invoices =
DISTINCTCOUNT(fact_invoice[invoice_id])
```

```dax
Total Purchase Orders =
DISTINCTCOUNT(fact_purchase_order[po_id])
```

```dax
Total Alerts =
COUNTROWS(fact_alert)
```

```dax
Potential Exposure =
SUM(fact_alert[estimated_exposure_inr])
```

```dax
High or Critical Alert Count =
CALCULATE(
    COUNTROWS(fact_alert),
    fact_alert[severity] IN {"High", "Critical"}
)
```

```dax
High or Critical Vendors =
CALCULATE(
    DISTINCTCOUNT(fact_vendor_risk[vendor_id]),
    fact_vendor_risk[risk_category] IN {"High", "Critical"}
)
```

On the seed-42 extract this measure is 0. The highest Python risk score is 34.38, which the model classifies as Medium. Leave the measure in the model so a later weight change can surface a High or Critical vendor without a page redesign.

```dax
Medium Risk Vendors =
CALCULATE(
    DISTINCTCOUNT(fact_vendor_risk[vendor_id]),
    fact_vendor_risk[risk_category] = "Medium"
)
```

```dax
Pending Review Alerts =
CALCULATE(
    COUNTROWS(fact_alert),
    fact_alert[review_status] = "Pending Review"
)
```

```dax
Data Quality Pass Rate =
DIVIDE(
    CALCULATE(
        COUNTROWS(fact_data_quality),
        fact_data_quality[passed] = TRUE()
    ),
    COUNTROWS(fact_data_quality)
)
```

```dax
Failed Quality Checks =
CALCULATE(
    COUNTROWS(fact_data_quality),
    fact_data_quality[passed] = FALSE()
)
```

```dax
Macro F1 =
AVERAGE(fact_rule_performance[f1_score])
```

`Macro F1` is the unweighted mean of the rule-level F1 scores already stored in the extract. On the verified seed-42 run that mean is 0.9584 across 17 rules. Put the words "synthetic rule evaluation" in the visual title. Do not title it "model accuracy".

```dax
Rule Precision =
SELECTEDVALUE(fact_rule_performance[precision])
```

```dax
Rule Recall =
SELECTEDVALUE(fact_rule_performance[recall])
```

```dax
Vendor Spend Share =
DIVIDE(
    SUM(fact_vendor_risk[spend_inr]),
    CALCULATE(SUM(fact_vendor_risk[spend_inr]), ALL(fact_vendor_risk))
)
```

```dax
Invoices This Month =
CALCULATE(
    DISTINCTCOUNT(fact_invoice[invoice_id]),
    USERELATIONSHIP(fact_invoice[invoice_date], dim_date[date])
)
```

`invoice_date` is the active relationship, so `USERELATIONSHIP` is only required for the inactive date roles below.

```dax
Payments on Payment Date =
CALCULATE(
    SUM(fact_payment[payment_amount_inr]),
    USERELATIONSHIP(fact_payment[payment_date], dim_date[date])
)
```

```dax
PO Amount on PO Date =
CALCULATE(
    SUM(fact_purchase_order[po_amount_inr]),
    USERELATIONSHIP(fact_purchase_order[po_date], dim_date[date])
)
```

```dax
Duplicate Invoice Alerts =
CALCULATE(
    COUNTROWS(fact_alert),
    fact_alert[rule_code] IN {
        "EXACT_DUP_INVOICE",
        "NEAR_TIME_DUP_INVOICE",
        "FUZZY_DUP_INVOICE"
    }
)
```

```dax
Invoice Benford MAD =
CALCULATE(
    AVERAGE(fact_benford[absolute_deviation]),
    fact_benford[population] = "non_recurring_invoices"
)
```

MAD is the mean of the per-digit absolute deviations. Keep the filter on `non_recurring_invoices`. The `employee_expenses` rows are a capped contrast population. A MAD above the marginal band is a digit-distribution observation, not a fraud conclusion.

```dax
Open Reconciliation Exceptions =
CALCULATE(
    COUNTROWS(fact_reconciliation),
    NOT fact_reconciliation[match_status] IN {
        "Matched",
        "Payment matched",
        "Non-PO below threshold",
        "Rejected purchase order"
    }
)
```

`Matched` is the purchase-order grain. `Payment matched` is the invoice grain. Non-PO invoices below the purchase-order threshold, and rejected orders, are expected states in this dataset.
