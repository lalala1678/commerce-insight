-- Append to analytics_scope.sql. First purchase is global, BEFORE dimension
-- filters, but never includes purchases after the selected historical cutoff.
, first_purchase AS (
    SELECT c.customer_unique_id, MIN(o.purchase_date) AS first_day
    FROM fact_order o JOIN dim_customer c ON c.customer_id = o.customer_id
    WHERE o.status = 'delivered' AND o.purchase_date <= :end_day
    GROUP BY c.customer_unique_id
)
SELECT s.customer_unique_id, MIN(f.first_day) AS first_day,
       MAX(s.purchase_date) AS last_day, COUNT(*) AS frequency,
       SUM(s.scoped_revenue_cents) AS monetary_cents
FROM scoped_orders s
JOIN first_purchase f ON f.customer_unique_id = s.customer_unique_id
GROUP BY s.customer_unique_id
