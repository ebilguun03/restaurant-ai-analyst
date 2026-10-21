-- How each menu group is trending month over month.
WITH by_group AS (
  SELECT menu_group, month, round(sum(net_sales), 2) AS net
  FROM fact_item_sales
  WHERE is_revenue AND line_type = 'menuItem'
  GROUP BY menu_group, month
)
SELECT
  menu_group,
  month,
  net,
  lag(net) OVER (PARTITION BY menu_group ORDER BY month) AS prev_month_net,
  round(100.0 * (net - lag(net) OVER (PARTITION BY menu_group ORDER BY month))
        / nullif(lag(net) OVER (PARTITION BY menu_group ORDER BY month), 0), 1) AS pct_change
FROM by_group
ORDER BY menu_group, month
