SELECT purchase_date AS day, COUNT(*) AS order_count,
       SUM(scoped_revenue_cents) AS revenue_cents
FROM scoped_orders GROUP BY purchase_date ORDER BY purchase_date
