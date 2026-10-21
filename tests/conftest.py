"""Shared test helpers: build a tiny fake Toast export in memory.

We never commit the restaurant's real sales files to git, so tests use a small
fake workbook with the same layout as a real Toast Product Mix export.
"""
import sys
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "transform"))

HEADER = [
    "Type", "Menu", "Menu group", "Subgroup", "Item, open item", "Size modifier",
    "Modifiers, special requests", "Item tags", "Qty sold", "Avg. price", "Item COGS",
    "Gross sales", "Discount amount", "Refund amount", "Void amount", "Net sales",
    "COGS", "Gross profit", "Gross margin (%)", "Tax", "Waste count", "Waste amount",
]


def _line(type_, menu, group, item, qty, price, gross, disc, net, tax):
    return [type_, menu, group, "", item, "", "", "", qty, price, "", gross, disc, 0.0, 0.0,
            net, "", "", "", tax, 0.0, 0.0]


def build_export(month="2026-01", total_net=None, title=None):
    """Return bytes of a fake ProductMix workbook. Totals are correct unless total_net is overridden."""
    items = [
        _line("menuItem", "Kitchen", "Yakitori", "Chicken Thigh", 10, 5.0, 50.0, 0.0, 50.0, 4.7),
        _line("menuItem", "Kitchen", "Yakitori", "Pork Belly", 4, 6.0, 24.0, 2.0, 22.0, 2.1),
        _line("menuItem", "Drinks", "Sake", "House Sake", 3, 9.0, 27.0, 0.0, 27.0, 2.5),
        _line("openItem", "Open items", "Open Drink", "Corkage Fee", 1, 15.0, 15.0, 0.0, 15.0, 0.0),
        _line("giftCard", "Gift card", "Gift card", "Gift Card", 1, 50.0, 50.0, 0.0, 50.0, 0.0),
    ]
    # Toast's grand total leaves gift cards out.
    rev_qty = 10 + 4 + 3 + 1
    rev_net = 50.0 + 22.0 + 27.0 + 15.0 if total_net is None else total_net

    wb = openpyxl.Workbook()
    summary = wb.active
    summary.title = "Summary"
    year, mon = month.split("-")
    summary.append([title or f"ProductMix_{month}-01_{month}-28"])
    summary.append(["-123 Test St, Suite #1 -Test Izakaya"])
    detail = wb.create_sheet("All levels")
    detail.append(HEADER)
    detail.append(_line("", "", "", "", rev_qty, 6.3, rev_net, 2.0, rev_net, 9.3))
    detail.append(_line("", "Kitchen", "", "", 14, 5.3, 74.0, 2.0, 72.0, 6.8))  # subtotal row
    for row in items:
        detail.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def export_bytes():
    return build_export()
