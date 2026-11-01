-- Employee expense screens. Weekend travel with a receipt is intentionally not an alert.

CREATE OR REPLACE VIEW vw_duplicate_expenses AS
SELECT
    left_row.expense_id AS left_expense_id,
    right_row.expense_id AS right_expense_id,
    left_row.employee_id,
    left_row.category,
    left_row.amount_inr,
    left_row.expense_date AS left_expense_date,
    right_row.expense_date AS right_expense_date
FROM employee_expenses AS left_row
JOIN employee_expenses AS right_row
    ON right_row.employee_id = left_row.employee_id
   AND right_row.category = left_row.category
   AND right_row.expense_id > left_row.expense_id
   AND ROUND(right_row.amount_inr, 2) = ROUND(left_row.amount_inr, 2)
WHERE left_row.amount_inr > 0
  AND ABS(right_row.expense_date - left_row.expense_date) <= 1;

CREATE OR REPLACE VIEW vw_threshold_gaming_expenses AS
WITH thresholds AS (
    SELECT * FROM (
        VALUES
            ('Meals', 5000::NUMERIC),
            ('Fuel', 8000::NUMERIC),
            ('Travel', 25000::NUMERIC),
            ('Lodging', 15000::NUMERIC),
            ('Client Entertainment', 10000::NUMERIC),
            ('Office Supplies', 3000::NUMERIC)
    ) AS seed(category, threshold_inr)
),
band AS (
    SELECT expense.*, thresholds.threshold_inr
    FROM employee_expenses AS expense
    JOIN thresholds ON thresholds.category = expense.category
    WHERE expense.amount_inr >= thresholds.threshold_inr * 0.90
      AND expense.amount_inr < thresholds.threshold_inr
),
dense AS (
    SELECT anchor.expense_id
    FROM band AS anchor
    JOIN band AS peer
        ON peer.employee_id = anchor.employee_id
       AND peer.category = anchor.category
       AND peer.expense_date BETWEEN anchor.expense_date - 90 AND anchor.expense_date + 90
    GROUP BY anchor.expense_id
    HAVING COUNT(*) >= 3
)
SELECT band.*
FROM band
JOIN dense ON dense.expense_id = band.expense_id;

CREATE OR REPLACE VIEW vw_offhours_expenses AS
SELECT *
FROM employee_expenses
WHERE amount_inr >= 2000
  AND receipt_attached = FALSE
  AND EXTRACT(DOW FROM submitted_at) IN (0, 6)
  AND (
        EXTRACT(HOUR FROM submitted_at) >= 22
        OR EXTRACT(HOUR FROM submitted_at) < 6
  );

CREATE OR REPLACE VIEW vw_self_approvals AS
SELECT
    approval.approval_id,
    approval.entity_type,
    approval.entity_id,
    approval.approver_employee_id,
    COALESCE(po.requestor_employee_id, expense.employee_id) AS owner_employee_id
FROM approval_records AS approval
LEFT JOIN purchase_orders AS po
    ON approval.entity_type = 'purchase_order'
   AND approval.entity_id = po.po_id
LEFT JOIN employee_expenses AS expense
    ON approval.entity_type = 'employee_expense'
   AND approval.entity_id = expense.expense_id
WHERE approval.decision = 'Approved'
  AND approval.approver_employee_id = COALESCE(po.requestor_employee_id, expense.employee_id);
