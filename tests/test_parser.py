import pytest

from conftest import build_export
from toast_parser import ParseError, make_item_key, month_from_title, parse_location, parse_product_mix


def test_parses_items_and_restaurant(export_bytes):
    result = parse_product_mix(export_bytes, "ProductMix_2026-01-01_2026-01-28.xlsx")
    assert result["month"] == "2026-01"
    assert result["restaurant"] == {
        "restaurant_id": "test-izakaya", "name": "Test Izakaya", "address": "123 Test St, Suite #1",
    }
    names = [r["item_name"] for r in result["rows"]]
    assert names == ["Chicken Thigh", "Pork Belly", "House Sake", "Corkage Fee", "Gift Card"]


def test_subtotal_rows_are_skipped(export_bytes):
    rows = parse_product_mix(export_bytes, "x.xlsx")["rows"]
    assert all(r["item_name"] for r in rows)
    assert len(rows) == 5


def test_gift_cards_are_kept_but_not_counted_as_revenue(export_bytes):
    result = parse_product_mix(export_bytes, "x.xlsx")
    gift = next(r for r in result["rows"] if r["line_type"] == "giftCard")
    assert gift["is_revenue"] is False
    assert result["check"]["net_sales"] == 114.0  # 50 + 22 + 27 + 15, no gift card


def test_rejects_file_whose_totals_dont_match():
    bad = build_export(total_net=999.0)
    with pytest.raises(ParseError, match="don't match"):
        parse_product_mix(bad, "x.xlsx")


def test_rejects_multi_month_export():
    with pytest.raises(ParseError, match="one calendar month"):
        month_from_title("ProductMix_2026-01-01_2026-02-28")


def test_rejects_non_excel_bytes():
    with pytest.raises(ParseError, match="not a readable"):
        parse_product_mix(b"hello", "notes.xlsx")


def test_item_key_is_stable_and_case_insensitive():
    assert make_item_key("Kitchen", "Yakitori", "Pork Belly") == make_item_key("kitchen", "YAKITORI", "pork belly")
    assert make_item_key("Kitchen", "Yakitori", "Pork Belly") != make_item_key("Kitchen", "Yakitori", "Chicken Thigh")


def test_parse_location_handles_toast_format():
    assert parse_location("-2120 S Highland Dr, Suite #15 -Ozora Izakaya Japanese Bar") == (
        "2120 S Highland Dr, Suite #15", "Ozora Izakaya Japanese Bar",
    )
