from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from config.loader import load_platforms
from core.grading import Grade, GradeLadder
from core.models import Inventory, Quote, utcnow
from services.opportunity_finder import OpportunityFinder, StrategyLimits

CONFIG = Path(__file__).resolve().parents[1] / "config" / "platforms.toml"
SPECS = load_platforms(CONFIG)


def quote(platform, side, price, *, age_seconds=0.0):
    return Quote(
        platform=platform,
        symbol="GLD_18C_750TMN",
        side=side,
        price_tmn_per_gram=Decimal(price),
        timestamp=utcnow() - timedelta(seconds=age_seconds),
    )


def rich(platform):
    return Inventory(
        platform=platform,
        cash_tmn=Decimal(50_000_000),
        gold_mg=5_000,
        updated_at=utcnow(),
    )


INVENTORIES = {n: rich(n) for n in SPECS}


def test_finds_a_profitable_route():
    finder = OpportunityFinder(SPECS)
    result = finder.find(
        [
            quote("miligold", "buy", 21_400_000),
            quote("miligold", "sell", 21_400_000),
            quote("wallgold", "buy", 21_900_000),
            quote("wallgold", "sell", 21_824_000),
        ],
        INVENTORIES,
    )

    assert result.best is not None
    opportunity = result.best.opportunity
    assert (opportunity.buy_platform, opportunity.sell_platform) == (
        "miligold",
        "wallgold",
    )
    assert opportunity.net_profit > 0
    assert result.best.grade.name in {"A", "B", "C", "D"}


def test_no_route_when_spread_is_negative():
    finder = OpportunityFinder(SPECS)
    result = finder.find(
        [
            quote("miligold", "buy", 21_900_000),
            quote("miligold", "sell", 21_900_000),
            quote("wallgold", "buy", 21_900_000),
            quote("wallgold", "sell", 21_800_000),
        ],
        INVENTORIES,
    )
    assert result.best is None
    assert "below_lowest_grade" in result.reason_counts()


def test_stale_quotes_are_rejected_not_traded():
    finder = OpportunityFinder(SPECS)
    result = finder.find(
        [
            quote("miligold", "buy", 21_400_000, age_seconds=120),
            quote("wallgold", "sell", 21_824_000, age_seconds=120),
        ],
        INVENTORIES,
    )
    assert result.best is None
    assert result.reason_counts()["stale_quote"] == 2


def test_grade_decides_how_much_capital_a_signal_gets():
    # A 1.70% net return, which earns grade A and so the full capital allowance.
    strong = [
        quote("miligold", "buy", 21_400_000),
        quote("wallgold", "sell", 21_960_000),
    ]
    result = OpportunityFinder(SPECS, StrategyLimits()).find(strong, INVENTORIES)
    assert result.best is not None
    assert result.best.grade.name == "A"
    full_size = result.best.opportunity.amount_mg

    # A 0.63% return earns a lower grade, and the lower grade is what makes it
    # trade smaller rather than not at all.
    thin = [
        quote("miligold", "buy", 21_400_000),
        quote("wallgold", "sell", 21_730_000),
    ]
    result = OpportunityFinder(SPECS, StrategyLimits()).find(thin, INVENTORIES)
    assert result.best is not None
    assert result.best.grade.name == "C"
    assert result.best.opportunity.amount_mg < full_size


def test_sizing_never_drops_below_the_fee_efficient_floor():
    """A lower grade must not shrink a trade into the punitive zone.

    WallGold bills a minimum of 400 mg. Grade D would allow only 15% of the
    ceiling, which is well under that, so sizing is held at the floor instead;
    trading smaller would raise the effective fee rather than reduce risk.
    """
    finder = OpportunityFinder(SPECS, StrategyLimits())
    result = finder.find(
        [
            quote("miligold", "buy", 21_400_000),
            quote("wallgold", "sell", 21_730_000),
        ],
        INVENTORIES,
    )
    assert result.best is not None
    assert result.best.opportunity.amount_mg >= 400


def test_ladder_must_not_give_worse_signals_more_capital():
    with pytest.raises(ValueError, match="more capital"):
        GradeLadder([
            Grade("A", Decimal("0.02"), Decimal("0.5")),
            Grade("B", Decimal("0.01"), Decimal("1.0")),
        ])


def test_size_search_evaluates_the_fee_kink():
    finder = OpportunityFinder(SPECS)
    sizes = finder.candidate_sizes(SPECS["miligold"], SPECS["wallgold"], 500)
    # WallGold's 0.4 g sell floor has to be one of the sizes considered, or the
    # search can miss the point where the effective rate finally drops.
    assert 400 in sizes
    assert 500 in sizes


def test_size_search_respects_the_coarser_step_of_the_pair():
    finder = OpportunityFinder(SPECS)
    # MelliGold's minimum sell is 10 mg, so every size for that route must clear
    # it and sit on the shared grid.
    sizes = finder.candidate_sizes(SPECS["wallgold"], SPECS["melligold"], 497)
    assert sizes and all(mg >= SPECS["melligold"].limits.min_order_mg for mg in sizes)


def test_inventory_caps_the_order_size():
    finder = OpportunityFinder(SPECS)
    inventories = dict(INVENTORIES)
    inventories["wallgold"] = Inventory(
        platform="wallgold",
        cash_tmn=Decimal(50_000_000),
        gold_mg=420,
        updated_at=utcnow(),
    )

    result = finder.find(
        [
            quote("miligold", "buy", 21_400_000),
            quote("wallgold", "sell", 21_824_000),
        ],
        inventories,
    )
    assert result.best is not None
    assert result.best.opportunity.amount_mg <= 420


def test_cash_shortage_is_reported_not_silently_dropped():
    finder = OpportunityFinder(SPECS)
    inventories = dict(INVENTORIES)
    inventories["miligold"] = Inventory(
        platform="miligold",
        cash_tmn=Decimal(500_000),
        gold_mg=5_000,
        updated_at=utcnow(),
    )

    result = finder.find(
        [
            quote("miligold", "buy", 21_400_000),
            quote("wallgold", "sell", 21_824_000),
        ],
        inventories,
    )
    assert result.best is None
    reasons = result.reason_counts()
    # The point is that the log says the size was capped by cash, not merely
    # that the (now tiny) trade was unprofitable.
    assert reasons["inventory_capped_size"] == 1
    detail = next(
        r.detail for r in result.rejections if r.reason == "inventory_capped_size"
    )
    assert detail.startswith("cash")


def test_disabled_venues_can_be_excluded_from_routing():
    finder = OpportunityFinder(SPECS)
    quotes = [
        quote("miligold", "buy", 21_400_000),
        quote("wallgold", "sell", 21_824_000),
        quote("goldika", "sell", 22_500_000),
    ]

    everything = finder.find(quotes, INVENTORIES)
    assert everything.best.opportunity.sell_platform == "goldika"

    # Restricting the tradable set is all it takes to route around a venue.
    without = finder.find(quotes, INVENTORIES, tradable={"miligold", "wallgold"})
    assert without.best.opportunity.sell_platform == "wallgold"
