import pytest

from sql_guard import UnsafeSQL, check_sql


@pytest.mark.parametrize("sql", [
    "SELECT sum(net_sales) FROM fact_item_sales WHERE month = '2026-03'",
    "select * from monthly_summary",
    "WITH g AS (SELECT menu_group, sum(net_sales) n FROM fact_item_sales GROUP BY 1) SELECT * FROM g",
    "SELECT d.item_name FROM fact_item_sales f JOIN dim_menu_item d ON d.item_key = f.item_key",
    "SELECT item_name FROM fact_item_sales WHERE item_name = 'Drop Shot Sake'",  # keyword inside a string is fine
])
def test_allows_read_only_queries(sql):
    assert check_sql(sql).lower().startswith(("select", "with"))


@pytest.mark.parametrize("sql,reason", [
    ("DROP TABLE fact_item_sales", "Only SELECT"),
    ("DELETE FROM fact_item_sales", "Only SELECT"),
    ("SELECT 1; DROP TABLE fact_item_sales", "one statement"),
    ("SELECT * FROM fact_item_sales -- harmless\n; DELETE FROM x", "one statement"),
    ("WITH x AS (SELECT 1) INSERT INTO fact_item_sales SELECT * FROM x", "not allowed"),
    ("SELECT * FROM information_schema.tables", "Unknown table"),
    ("SELECT * FROM other_db.secrets", "Unknown table"),
    ("", "Empty"),
])
def test_blocks_unsafe_queries(sql, reason):
    with pytest.raises(UnsafeSQL, match=reason):
        check_sql(sql)


def test_adds_limit_when_missing():
    assert check_sql("SELECT * FROM fact_item_sales").endswith("LIMIT 200")


def test_keeps_existing_limit():
    out = check_sql("SELECT * FROM fact_item_sales LIMIT 5")
    assert out.endswith("LIMIT 5") and "LIMIT 200" not in out
