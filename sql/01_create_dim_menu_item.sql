-- Dimension: one row per menu item (latest name and grouping seen).
-- Run once after deploying. Together with fact_item_sales this forms a small star schema.
CREATE OR REPLACE VIEW dim_menu_item AS
SELECT
  item_key,
  max_by(item_name, month)  AS item_name,
  max_by(menu, month)       AS menu,
  max_by(menu_group, month) AS menu_group,
  max_by(line_type, month)  AS line_type,
  min(month)                AS first_month_sold,
  max(month)                AS last_month_sold
FROM fact_item_sales
GROUP BY item_key
