-- One row per restaurant per month: the numbers an owner checks first.
-- Gift cards are excluded from revenue (Toast does the same).
CREATE OR REPLACE VIEW monthly_summary AS
SELECT
  restaurant_id,
  month,
  sum(qty_sold)                         AS items_sold,
  round(sum(net_sales), 2)              AS net_sales,
  round(sum(discount_amount), 2)        AS discounts,
  round(sum(void_amount), 2)            AS voids,
  round(sum(net_sales) / sum(qty_sold), 2) AS avg_item_price
FROM fact_item_sales
WHERE is_revenue
GROUP BY restaurant_id, month
