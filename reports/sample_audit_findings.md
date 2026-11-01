# Sample audit findings

Each item below is a synthetic screening alert. Review status starts at Pending Review.
None of these items is a confirmed fraud, a real loss, or a real vendor.

## ALT000020 — Duplicate full payment

- Rule: DUP_PAYMENT
- Severity: Critical
- Entity: payment PAY001389
- Vendor: VEN047
- Employee: n/a
- Potential exposure (INR): 344,419.58
- Review status: Pending Review
- Reason: More than one completed payment covers essentially the full invoice total.
- Evidence: {"invoice_id": "INV000520", "invoice_total_inr": 344419.58, "payment_amounts_inr": [344419.58, 344419.58], "payment_ids": ["PAY000011", "PAY001389"]}

## ALT000013 — Duplicate full payment

- Rule: DUP_PAYMENT
- Severity: Critical
- Entity: payment PAY001382
- Vendor: VEN045
- Employee: n/a
- Potential exposure (INR): 329,420.51
- Review status: Pending Review
- Reason: More than one completed payment covers essentially the full invoice total.
- Evidence: {"invoice_id": "INV000919", "invoice_total_inr": 329420.51, "payment_amounts_inr": [329420.51, 329420.51], "payment_ids": ["PAY000003", "PAY001382"]}

## ALT000014 — Duplicate full payment

- Rule: DUP_PAYMENT
- Severity: Critical
- Entity: payment PAY001383
- Vendor: VEN056
- Employee: n/a
- Potential exposure (INR): 311,326.86
- Review status: Pending Review
- Reason: More than one completed payment covers essentially the full invoice total.
- Evidence: {"invoice_id": "INV000511", "invoice_total_inr": 311326.86, "payment_amounts_inr": [311326.86, 311326.86], "payment_ids": ["PAY000004", "PAY001383"]}

## ALT000026 — Self-approval conflict

- Rule: SELF_APPROVAL
- Severity: Critical
- Entity: approval_record APR000220
- Vendor: VEN045
- Employee: EMP004
- Potential exposure (INR): 101,000.00
- Review status: Pending Review
- Reason: The approver is the same employee who requested the purchase or submitted the claim.
- Evidence: {"approval_id": "APR000220", "approver_employee_id": "EMP004", "entity_id": "PO000230", "entity_type": "purchase_order", "owner_employee_id": "EMP004"}

## ALT000025 — Self-approval conflict

- Rule: SELF_APPROVAL
- Severity: Critical
- Entity: approval_record APR000219
- Vendor: VEN044
- Employee: EMP003
- Potential exposure (INR): 99,800.00
- Review status: Pending Review
- Reason: The approver is the same employee who requested the purchase or submitted the claim.
- Evidence: {"approval_id": "APR000219", "approver_employee_id": "EMP003", "entity_id": "PO000229", "entity_type": "purchase_order", "owner_employee_id": "EMP003"}

## ALT000024 — Self-approval conflict

- Rule: SELF_APPROVAL
- Severity: Critical
- Entity: approval_record APR000218
- Vendor: VEN043
- Employee: EMP002
- Potential exposure (INR): 98,600.00
- Review status: Pending Review
- Reason: The approver is the same employee who requested the purchase or submitted the claim.
- Evidence: {"approval_id": "APR000218", "approver_employee_id": "EMP002", "entity_id": "PO000228", "entity_type": "purchase_order", "owner_employee_id": "EMP002"}

## ALT000023 — Self-approval conflict

- Rule: SELF_APPROVAL
- Severity: Critical
- Entity: approval_record APR000217
- Vendor: VEN042
- Employee: EMP004
- Potential exposure (INR): 97,400.00
- Review status: Pending Review
- Reason: The approver is the same employee who requested the purchase or submitted the claim.
- Evidence: {"approval_id": "APR000217", "approver_employee_id": "EMP004", "entity_id": "PO000227", "entity_type": "purchase_order", "owner_employee_id": "EMP004"}

## ALT000022 — Self-approval conflict

- Rule: SELF_APPROVAL
- Severity: Critical
- Entity: approval_record APR000216
- Vendor: VEN041
- Employee: EMP003
- Potential exposure (INR): 96,200.00
- Review status: Pending Review
- Reason: The approver is the same employee who requested the purchase or submitted the claim.
- Evidence: {"approval_id": "APR000216", "approver_employee_id": "EMP003", "entity_id": "PO000226", "entity_type": "purchase_order", "owner_employee_id": "EMP003"}
