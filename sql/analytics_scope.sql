-- Bound timestamps form [start_at, end_at); category/state may be ''.
-- Items -> order totals before joining order facts. Raw payments/reviews never
-- enter this query: ETL has already folded them to one row per order.
WITH scoped_items AS (
    SELECT i.order_id, i.item_id, i.product_id, i.seller_id,
           i.price_cents, i.freight_cents,
           p.category, COALESCE(p.category_english, p.category) AS category_label,
           c.state
    FROM fact_item i
    JOIN fact_order o ON o.order_id = i.order_id
    JOIN dim_product p ON p.product_id = i.product_id
    JOIN dim_customer c ON c.customer_id = o.customer_id
    WHERE o.status = 'delivered'
      -- ETL derives purchase_date from purchase_at; this equivalent predicate
      -- makes the existing (status, purchase_date) index usable for date ranges.
      AND o.purchase_date >= :start_day AND o.purchase_date <= :end_day
      AND o.purchase_at >= :start_at AND o.purchase_at < :end_at
      AND (:category = '' OR p.category = :category)
      AND (:state = '' OR c.state = :state)
), item_totals AS (
    SELECT order_id, SUM(price_cents) AS scoped_revenue_cents, COUNT(*) AS scoped_item_count
    FROM scoped_items GROUP BY order_id
), scoped_orders AS (
    SELECT o.*, c.customer_unique_id, c.state,
           t.scoped_revenue_cents, t.scoped_item_count
    FROM item_totals t
    JOIN fact_order o ON o.order_id = t.order_id
    JOIN dim_customer c ON c.customer_id = o.customer_id
)
