-- Split-purchase islands and repeated near-threshold orders.
-- An island is a date-ordered chain whose consecutive gaps are within 14 days.
-- Combined value is compared with the highest limit that actually approved a member.
-- Orders with sufficient authority stay in the view and are not treated as alerts.

CREATE OR REPLACE VIEW vw_split_purchase_clusters AS
WITH params AS (
    SELECT 200000::NUMERIC AS threshold, 14 AS window_days
),
eligible AS (
    SELECT po.*
    FROM purchase_orders AS po
    CROSS JOIN params
    WHERE po.po_amount_inr < params.threshold
      AND po.status IN ('Approved', 'Closed')
),
ordered AS (
    SELECT
        eligible.*,
        LAG(eligible.po_date) OVER (
            PARTITION BY vendor_id, department, category
            ORDER BY po_date, po_id
        ) AS previous_date
    FROM eligible
),
marked AS (
    SELECT
        ordered.*,
        CASE
            WHEN previous_date IS NULL OR (po_date - previous_date) > (SELECT window_days FROM params)
                THEN 1
            ELSE 0
        END AS new_island
    FROM ordered
),
islands AS (
    SELECT
        marked.*,
        SUM(new_island) OVER (
            PARTITION BY vendor_id, department, category
            ORDER BY po_date, po_id
        ) AS island_number
    FROM marked
),
approver_limits AS (
    SELECT
        approval.entity_id AS po_id,
        MAX(employee.approval_limit_inr) AS max_limit
    FROM approval_records AS approval
    JOIN employees AS employee ON employee.employee_id = approval.approver_employee_id
    WHERE approval.entity_type = 'purchase_order'
      AND approval.decision = 'Approved'
    GROUP BY approval.entity_id
),
rolled AS (
    SELECT
        islands.vendor_id,
        islands.department,
        islands.category,
        islands.island_number,
        COUNT(*) AS po_count,
        SUM(islands.po_amount_inr) AS cluster_sum_inr,
        MIN(islands.po_id) AS anchor_po_id,
        COALESCE(MAX(approver_limits.max_limit), 0) AS max_approver_limit_inr
    FROM islands
    LEFT JOIN approver_limits ON approver_limits.po_id = islands.po_id
    GROUP BY islands.vendor_id, islands.department, islands.category, islands.island_number
    HAVING COUNT(*) >= 2
       AND SUM(islands.po_amount_inr) >= (SELECT threshold FROM params)
)
SELECT
    'SPC-' || rolled.anchor_po_id AS cluster_id,
    islands.po_id,
    islands.vendor_id,
    islands.department,
    islands.category,
    islands.po_date,
    islands.po_amount_inr,
    rolled.cluster_sum_inr,
    rolled.max_approver_limit_inr,
    CASE
        WHEN rolled.max_approver_limit_inr < rolled.cluster_sum_inr THEN 'insufficient_approval'
        ELSE 'adequate_approval'
    END AS disposition
FROM islands
JOIN rolled
    ON rolled.vendor_id = islands.vendor_id
   AND rolled.department = islands.department
   AND rolled.category = islands.category
   AND rolled.island_number = islands.island_number;

CREATE OR REPLACE VIEW vw_threshold_gaming_purchase_orders AS
WITH band AS (
    SELECT *
    FROM purchase_orders
    WHERE po_amount_inr >= 180000
      AND po_amount_inr < 200000
),
dense AS (
    SELECT anchor.po_id
    FROM band AS anchor
    JOIN band AS peer
        ON peer.vendor_id = anchor.vendor_id
       AND peer.po_date BETWEEN anchor.po_date - 90 AND anchor.po_date + 90
    GROUP BY anchor.po_id
    HAVING COUNT(*) >= 3
)
SELECT band.*
FROM band
JOIN dense ON dense.po_id = band.po_id;
