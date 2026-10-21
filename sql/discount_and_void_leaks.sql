-- Items losing the most money to voids and discounts (possible kitchen or training issues).
SELECT
  item_name,
  menu_group,
  sum(qty_sold)                    AS qty,
  round(sum(void_amount), 2)       AS voided,
  round(sum(discount_amount), 2)   AS discounted,
  round(100.0 * sum(void_amount) / nullif(sum(gross_sales), 0), 1) AS void_pct_of_gross
FROM fact_item_sales
WHERE line_type = 'menuItem'
GROUP BY item_name, menu_group
HAVING sum(void_amount) + sum(discount_amount) > 0
ORDER BY sum(void_amount) + sum(discount_amount) DESC
LIMIT 20
