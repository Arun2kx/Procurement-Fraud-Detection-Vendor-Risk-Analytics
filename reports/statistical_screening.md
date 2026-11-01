# Statistical screening note

Benford and outlier screens are not fraud alerts.

## Non-recurring invoices

- Applicable: True
- Sample size: 875
- Chi-square: 26.9547
- p-value: 0.0007198301920641583
- Mean absolute deviation: 0.01408
- Conformity band: marginal_conformity
- Limitation: Mean absolute deviation bands follow a common audit heuristic (close, acceptable, marginal, nonconformity). They are not a legal or statistical proof of fraud. Capped, priced-from-a-catalogue, or recurring amounts are poor Benford populations.

## Employee expenses

- Applicable: True
- Sample size: 815
- Chi-square: 54.7807
- p-value: 4.8699912115590984e-09
- Mean absolute deviation: 0.018994
- Conformity band: nonconformity
- Limitation: Employee expenses are bounded by category thresholds and receipt rules. A Benford deviation in this population is expected to be ambiguous and is not used as an alert.

Category-adjusted statistical outlier rows written: 250.
