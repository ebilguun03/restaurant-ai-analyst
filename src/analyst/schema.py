"""What the AI is told about the data. Clear descriptions here matter more than clever prompts."""

SCHEMA = """
Database: Amazon Athena (Trino SQL dialect). Data is monthly menu sales from a Toast POS
for one restaurant (Ozora Izakaya). Months currently loaded: 2026-01, 2026-02, 2026-03.

TABLE fact_item_sales  -- one row per menu item per month
  month            string   'YYYY-MM' (partition column, filter on it when you can)
  restaurant_id    string
  item_key         string   stable id for an item, joins to dim_menu_item
  item_name        string
  menu             string   'Kitchen', 'Drinks', 'Weekly Special', 'Lunch Specials', 'Open items', 'Gift card'
  menu_group       string   e.g. 'Specialty Rolls', 'Yakitori', 'Appetizers', 'Desserts', 'Sake', 'Beer'
  subgroup         string
  line_type        string   'menuItem' (on the menu), 'openItem' (custom item rung in by staff), 'giftCard'
  is_revenue       boolean  FALSE only for gift cards
  qty_sold         int
  avg_price        double
  gross_sales      double   before discounts
  discount_amount  double
  refund_amount    double
  void_amount      double   value of items voided (cancelled) by staff
  net_sales        double   gross minus discounts and refunds; THIS is "sales" unless asked otherwise
  tax              double

VIEW monthly_summary  -- one row per month, revenue lines only
  restaurant_id, month, items_sold, net_sales, discounts, voids, avg_item_price

VIEW dim_menu_item  -- one row per item
  item_key, item_name, menu, menu_group, line_type, first_month_sold, last_month_sold

Business rules:
  * "Sales" or "revenue" means SUM(net_sales) WHERE is_revenue = TRUE. Gift cards are not revenue.
  * Questions about dishes, drinks or menu items: use line_type = 'menuItem'.
  * Data is monthly totals only. There is no day, weekday, hour, customer or server data.
"""
