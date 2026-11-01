# Synthetic detection evaluation

These figures compare the screening rules with planted synthetic labels.
They are not a real-world fraud-detection accuracy rate, and no alert is a confirmed fraud.
A false positive here includes benign controls and ordinary records the generator did not mark as suspicious.
A false negative includes planted suspicious records the rule is designed to miss, such as near-duplicates that use the next serial invoice number.

| Rule | Positives | Alerts | TP | FP | FN | TN | Precision | Recall | F1 | FPR | Benign controls flagged |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EXACT_DUP_INVOICE | 16 | 16 | 16 | 0 | 0 | 1482 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| NEAR_TIME_DUP_INVOICE | 28 | 20 | 20 | 0 | 8 | 1470 | 1.0000 | 0.7143 | 0.8333 | 0.0000 | 0 |
| FUZZY_DUP_INVOICE | 16 | 16 | 16 | 0 | 0 | 1482 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| SPLIT_PURCHASE | 21 | 21 | 21 | 0 | 0 | 829 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| THRESHOLD_GAMING | 12 | 12 | 12 | 0 | 0 | 838 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| DUP_PAYMENT | 20 | 20 | 20 | 0 | 0 | 1380 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| EARLY_PAYMENT | 5 | 8 | 5 | 3 | 0 | 1392 | 0.6250 | 1.0000 | 0.7692 | 0.0022 | 3 |
| LATE_PAYMENT | 15 | 21 | 15 | 6 | 0 | 1379 | 0.7143 | 1.0000 | 0.8333 | 0.0043 | 6 |
| PAYMENT_MISMATCH | 5 | 5 | 5 | 0 | 0 | 1395 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| DUPLICATE_EXPENSE | 16 | 16 | 16 | 0 | 0 | 884 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| THRESHOLD_GAMING_EXPENSE | 20 | 20 | 20 | 0 | 0 | 880 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| OFFHOURS_EXPENSE | 12 | 16 | 12 | 4 | 0 | 884 | 0.7500 | 1.0000 | 0.8571 | 0.0045 | 4 |
| SELF_APPROVAL | 14 | 14 | 14 | 0 | 0 | 1771 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| PO_APPROVAL_LIMIT_BREACH | 8 | 8 | 8 | 0 | 0 | 842 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| PO_MISSING_APPROVAL | 10 | 10 | 10 | 0 | 0 | 840 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| PRICE_VOLATILITY | 3 | 3 | 3 | 0 | 0 | 57 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |
| HIGH_DISPUTE_RATE | 4 | 4 | 4 | 0 | 0 | 56 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |

## How to read the macro average

The unweighted mean of available F1 scores treats a date-logic rule and a judgmental rule as equal.
It is a summary of this synthetic test, not a claim about operational performance.

Unweighted mean F1 across 17 rules with a defined score: 0.9584.
