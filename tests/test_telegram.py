from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from config.loader import load_platforms
from core.grading import DEFAULT_LADDER
from core.models import Inventory, Opportunity, Quote, utcnow
from services.opportunity_finder import GradedOpportunity, OpportunityFinder
from services.telegram import (
    format_market_report,
    format_scan_summary,
    format_trade_result,
    format_trade_signal,
    route_edges,
    venue_lines,
)

SPECS = load_platforms(Path(__file__).resolve().parents[1] / "config" / "platforms.toml")


def quotes_for(prices: dict[str, tuple[int, int]]) -> list[Quote]:
    now = utcnow()
    out = []
    for platform, (buy, sell) in prices.items():
        for side, price in (("buy", buy), ("sell", sell)):
            out.append(
                Quote(
                    platform=platform,
                    symbol="GLD_18C_750TMN",
                    side=side,
                    price_tmn_per_gram=Decimal(price),
                    timestamp=now,
                )
            )
    return out


LIVE = {
    "wallgold": (22_183_000, 22_183_000),
    "melligold": (22_053_640, 22_053_640),
    "talasea": (22_245_000, 22_245_000),
    "goldika": (22_372_717, 21_842_139),
    "miligold": (21_553_000, 21_553_000),
}


def test_report_covers_every_venue_in_the_scan():
    text = format_market_report(quotes_for(LIVE), SPECS)
    for name in ("WallGold", "MelliGold", "Talasea", "Goldika", "MilliGold"):
        assert name in text


def test_adding_a_venue_needs_no_change_here():
    # The whole point of the rewrite: a venue the formatter has never heard of
    # still appears, because nothing in this module names one.
    subset = {"wallgold": LIVE["wallgold"], "melligold": LIVE["melligold"]}
    assert "Talasea" not in format_market_report(quotes_for(subset), SPECS)
    assert "Talasea" in format_market_report(quotes_for(LIVE), SPECS)


def test_a_missing_venue_does_not_cost_us_the_report():
    partial = quotes_for(LIVE)
    # Drop WallGold's sell side, as if that one call had timed out.
    partial = [q for q in partial if not (q.platform == "wallgold" and q.side == "sell")]
    text = format_market_report(partial, SPECS)
    assert "MelliGold" in text
    assert "WallGold" not in text


def test_unverified_venues_are_marked_scan_only():
    text = format_market_report(quotes_for(LIVE), SPECS)
    assert "scan only" in text


def test_report_states_the_shortfall_when_nothing_is_profitable():
    text = format_market_report(
        quotes_for({k: v for k, v in LIVE.items() if k != "miligold"}), SPECS
    )
    assert "No profitable route" in text
    assert "short by" in text


def test_prices_shown_are_all_in_not_raw():
    lines = {line.spec.name: line for line in venue_lines(quotes_for(LIVE), SPECS)}
    wall = lines["wallgold"]
    # A single reference price plus a 0.5% fee each way, so the all-in buy sits
    # above the quote and the all-in sell below it.
    assert wall.net_buy > Decimal(22_183_000)
    assert wall.net_sell < Decimal(22_183_000)
    assert wall.round_trip > 0


def test_routes_are_ranked_best_first():
    edges = route_edges(venue_lines(quotes_for(LIVE), SPECS))
    assert edges == sorted(edges, key=lambda r: r[2], reverse=True)
    assert edges[0][0] == "MilliGold"


def test_signal_names_the_grade_and_the_allowance():
    finder = OpportunityFinder(SPECS)
    inventories = {
        name: Inventory(name, Decimal(50_000_000), 5_000, utcnow()) for name in SPECS
    }
    result = finder.find(
        quotes_for({"miligold": (21_400_000, 21_400_000),
                    "wallgold": (21_960_000, 21_960_000)}),
        inventories,
    )
    assert result.best is not None
    text = format_trade_signal(result.best)
    assert f"GRADE {result.best.grade.name}" in text
    assert "allowance" in text


def test_partial_execution_says_it_needs_a_human():
    graded = GradedOpportunity(
        Opportunity(
            buy_platform="miligold",
            sell_platform="wallgold",
            symbol="GLD_18C_750TMN",
            amount_mg=500,
            buy_price=Decimal(21_400_000),
            sell_price=Decimal(21_960_000),
            buy_fee=Decimal(42_800),
            sell_fee=Decimal(54_900),
            timestamp=utcnow(),
        ),
        DEFAULT_LADDER.grades[0],
    )
    text = format_trade_result(graded, {"status": "partial_execution", "stage": "sell"})
    assert "TRADING HALTED" in text
    assert "needs a human" in text


def test_scan_summary_groups_rejection_reasons():
    finder = OpportunityFinder(SPECS)
    stale = [
        Quote("wallgold", "GLD_18C_750TMN", "buy", Decimal(22_183_000),
              utcnow() - timedelta(minutes=5)),
        Quote("melligold", "GLD_18C_750TMN", "sell", Decimal(22_053_640),
              utcnow() - timedelta(minutes=5)),
    ]
    inventories = {
        name: Inventory(name, Decimal(50_000_000), 5_000, utcnow()) for name in SPECS
    }
    summary = format_scan_summary(finder.find(stale, inventories))
    assert "stale_quote" in summary
