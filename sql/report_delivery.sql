-- Exactly one category per order: largest selected merchandise subtotal;
-- ties resolve by category name. This partition is not item-level attribution.
, category_amount AS (
  SELECT order_id, category, SUM(price_cents) AS cents
  FROM scoped_items GROUP BY order_id, category
), category_rank AS (
  SELECT order_id, category,
         ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY cents DESC, category) AS rn
  FROM category_amount
)
SELECT c.category, o.state, o.is_late, o.review_score, COUNT(*) AS order_count
FROM scoped_orders o JOIN category_rank c ON c.order_id=o.order_id AND c.rn=1
GROUP BY c.category, o.state, o.is_late, o.review_score
