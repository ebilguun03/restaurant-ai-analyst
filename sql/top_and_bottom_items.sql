-- Best and worst sellers by net sales over every month loaded.
WITH totals AS (
  SELECT d.item_name, d.menu_group,
         sum(f.qty_sold)            AS qty,
         round(sum(f.net_sales), 2) AS net
  FROM fact_item_sales f
  JOIN dim_menu_item d ON d.item_key = f.item_key
  WHERE f.is_revenue AND f.line_type = 'menuItem'
  GROUP BY d.item_name, d.menu_group
)
SELECT *, rank() OVER (ORDER BY net DESC) AS sales_rank
FROM totals
ORDER BY net DESC
