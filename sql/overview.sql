-- 先聚合到订单粒度，避免同一订单多件商品导致订单数膨胀。
-- 示例金额使用整数分；不含运费；取消和处理中订单不进入分子或分母。
WITH order_totals AS (
    SELECT o.order_id, SUM(i.price_cents) AS amount_cents
    FROM demo_orders o
    JOIN demo_items i ON o.order_id = i.order_id
    WHERE o.status = 'delivered'
    GROUP BY o.order_id
)
SELECT COUNT(*) AS order_count, COALESCE(SUM(amount_cents), 0) AS revenue_cents
FROM order_totals;
