import sqlite3
from decimal import Decimal

from core.grading import DEFAULT_LADDER
from core.models import Inventory, Opportunity, utcnow
from services.opportunity_finder import GradedOpportunity
from services.paper import SCHEMA, PaperBook, real_inventory_blocks


def opportunity(buy="miligold", sell="wallgold", amount_mg=500):
    return Opportunity(
        buy_platform=buy, sell_platform=sell, symbol="GLD_18C_750TMN",
        amount_mg=amount_mg, buy_price=Decimal(21_400_000), sell_price=Decimal(21_960_000),
        buy_fee=Decimal(42_800), sell_fee=Decimal(54_900), timestamp=utcnow(),
    )


def graded(**kw):
    return GradedOpportunity(opportunity(**kw), DEFAULT_LADDER.grades[0])


def book():
    return PaperBook({"miligold": (Decimal(30_000_000), 2_000),
                      "wallgold": (Decimal(30_000_000), 2_000)})


def test_a_fill_moves_gold_and_cash_in_opposite_directions():
    b = book()
    g = graded()
    b.fill(g)

    buy_cash, buy_gold = b.balances["miligold"]
    sell_cash, sell_gold = b.balances["wallgold"]

    assert buy_gold == 2_500          # bought gold sits on the buy venue
    assert sell_gold == 1_500         # sold gold leaves the sell venue
    assert buy_cash < Decimal(30_000_000)
    assert sell_cash > Decimal(30_000_000)


def test_repeating_one_route_drains_the_book():
    """The drift, not the edge, is what stops the strategy.

    Each fill spends cash on the buy venue and gold on the sell venue, and
    neither comes back without an external transfer. Here the buy venue's cash
    is what runs out first, after two fills of a 30M book.
    """
    b = book()
    fills = 0
    while b.can_fill(graded()):
        b.fill(graded())
        fills += 1

    assert fills == 2
    assert b.balances["miligold"][0] < opportunity().required_cash
    assert b.balances["miligold"][1] > 2_000     # gold piled up where we buy
    assert b.balances["wallgold"][1] < 2_000     # and drained where we sell


def test_paper_profit_shows_up_in_the_marked_book():
    b = book()
    mark = Decimal(21_960_000)
    before = b.value(mark)
    b.fill(graded())
    assert b.value(mark) > before


def test_real_inventory_block_names_the_shortfall():
    now = utcnow()
    real = {
        "miligold": Inventory("miligold", Decimal(431_809), 1_004, now),
        "wallgold": Inventory("wallgold", Decimal(10_985_795), 3_699, now),
    }
    reason = real_inventory_blocks(graded(), real)
    assert "miligold short" in reason
    assert "TMN" in reason


def test_gold_shortfall_is_reported_too():
    now = utcnow()
    real = {
        "miligold": Inventory("miligold", Decimal(50_000_000), 5_000, now),
        "wallgold": Inventory("wallgold", Decimal(0), 100, now),
    }
    assert real_inventory_blocks(graded(), real) == "wallgold short 400mg gold"


def test_no_block_when_the_balances_cover_it():
    now = utcnow()
    real = {
        "miligold": Inventory("miligold", Decimal(50_000_000), 5_000, now),
        "wallgold": Inventory("wallgold", Decimal(0), 5_000, now),
    }
    assert real_inventory_blocks(graded(), real) == ""


def test_book_survives_a_restart():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)

    b = book()
    b.fill(graded())
    b.save(conn)

    restored = PaperBook.load(conn, ["miligold", "wallgold"])
    assert restored.balances == b.balances
