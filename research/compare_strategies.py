"""Cash-Slot Rotation against pairwise net-edge scanning.

This is a structural demonstration, not a backtest. No historical bid/ask series
exists for these venues, so the prices below are single observations, each
labelled with where it came from. The point being made does not depend on the
level of the prices, only on the shape of the spreads.

Run: python -m research.compare_strategies
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from config.loader import load_platforms
from core.fees import fee_tmn
from core.models import Inventory, Quote, utcnow
from services.opportunity_finder import OpportunityFinder, StrategyLimits

SPECS = load_platforms(Path(__file__).resolve().parents[1] / "config" / "platforms.toml")

GRAM_MG = 1000


@dataclass(frozen=True)
class Observation:
    """One venue's raw quotes at a point in time."""

    platform: str
    ask: Decimal  # what we pay per gram, before fees
    bid: Decimal  # what we receive per gram, before fees
    source: str


# Measured live from the public price endpoints on 2026-08-31 13:30 UTC.
#   goldika: /api/public/price -> buy 225082172, sell 219744254 (rial)
#   miligold: /api/v1/public/milli-price/detail -> price18 217680
# WallGold's price endpoint needs an authenticated session, so its numbers come
# from the confirmed fill recorded in real_trade_once.log on 2026-08-25.
SNAPSHOT = [
    Observation("goldika", Decimal(22_508_217), Decimal(21_974_425), "live 08-31"),
    Observation("miligold", Decimal(21_768_000), Decimal(21_768_000), "live 08-31"),
    Observation("wallgold", Decimal(21_900_000), Decimal(21_824_000), "log 08-25"),
]


def net_buy(obs: Observation, amount_mg: int) -> Decimal:
    """All-in cost per gram of acquiring gold on this venue."""
    fee = fee_tmn(SPECS[obs.platform].buy_fee, amount_mg, obs.ask)
    return obs.ask + fee * GRAM_MG / amount_mg


def net_sell(obs: Observation, amount_mg: int) -> Decimal:
    """All-in proceeds per gram of disposing of gold on this venue."""
    fee = fee_tmn(SPECS[obs.platform].sell_fee, amount_mg, obs.bid)
    return obs.bid - fee * GRAM_MG / amount_mg


def show_executable_prices(observations: list[Observation], amount_mg: int) -> None:
    print(f"Executable prices at {amount_mg} mg (TMN per gram)\n")
    print(f"{'venue':<10} {'NetBuy':>14} {'NetSell':>14} {'round-trip':>12}  source")
    print("-" * 70)
    for obs in observations:
        nb, ns = net_buy(obs, amount_mg), net_sell(obs, amount_mg)
        print(
            f"{obs.platform:<10} {nb:>14,.0f} {ns:>14,.0f} "
            f"{nb - ns:>12,.0f}  {obs.source}"
        )
    print()


def rotation_choice(observations: list[Observation], amount_mg: int) -> Observation:
    """The doc's rule: the venue with the highest executable sell price is cash.

    Section 13, step 3: "Identify candidate expensive platform B using executable
    sell price". A single-sided ranking.
    """
    return max(observations, key=lambda o: net_sell(o, amount_mg))


def cheapest_place_to_buy(observations: list[Observation], amount_mg: int) -> Observation:
    return min(observations, key=lambda o: net_buy(o, amount_mg))


def demonstrate_rotation_trap(observations: list[Observation], amount_mg: int) -> None:
    print("What the rotation rule does with these prices\n")

    cash_venue = rotation_choice(observations, amount_mg)
    best_buy = cheapest_place_to_buy(observations, amount_mg)

    print(f"  Highest NetSell -> cash sits on {cash_venue.platform}")
    print(f"  Under rotation, {cash_venue.platform} is therefore the only venue")
    print("  we can buy on, because it holds all the cash.\n")

    forced = net_buy(cash_venue, amount_mg)
    available = net_buy(best_buy, amount_mg)
    penalty = forced - available

    print(f"  Forced buy price   ({cash_venue.platform:<9}) {forced:>14,.0f}")
    print(f"  Cheapest available ({best_buy.platform:<9}) {available:>14,.0f}")
    print(f"  Penalty per gram                {penalty:>14,.0f}", end="")
    print(f"   ({penalty / available * 100:.2f}%)\n")

    if penalty > 0:
        print(
            "  The venue with the best bid also has the worst ask, because its\n"
            "  spread is wide on both sides. Ranking on one side of the market\n"
            "  parks the cash exactly where it is most expensive to deploy.\n"
        )
    else:
        print("  On this snapshot the ranking happens to be harmless.\n")


def demonstrate_pairwise(observations: list[Observation], amount_mg: int) -> None:
    print("What pairwise net-edge scanning does with the same prices\n")

    rows = []
    for buy in observations:
        for sell in observations:
            if buy.platform == sell.platform:
                continue
            edge = net_sell(sell, amount_mg) - net_buy(buy, amount_mg)
            rows.append((buy.platform, sell.platform, edge))

    rows.sort(key=lambda r: r[2], reverse=True)

    print(f"  {'route':<24} {'edge per gram':>16}")
    print("  " + "-" * 42)
    for buy, sell, edge in rows:
        print(f"  {buy + ' -> ' + sell:<24} {edge:>16,.0f}")

    best = rows[0]
    print()
    if best[2] > 0:
        print(f"  Best route {best[0]} -> {best[1]} at {best[2]:,.0f}/gram.")
    else:
        print(
            "  Every route is negative, so pairwise scanning trades nothing and\n"
            "  leaves the inventory where it is. Rotation, by contrast, would\n"
            "  still move cash because the ranking changed.\n"
        )


def demonstrate_finder(observations: list[Observation]) -> None:
    """The same logic through the actual production code path."""
    print("Through OpportunityFinder\n")

    quotes: list[Quote] = []
    for obs in observations:
        for side, price in (("buy", obs.ask), ("sell", obs.bid)):
            quotes.append(
                Quote(
                    platform=obs.platform,
                    symbol="GLD_18C_750TMN",
                    side=side,
                    price_tmn_per_gram=price,
                    timestamp=utcnow(),
                )
            )

    inventories = {
        obs.platform: Inventory(
            platform=obs.platform,
            cash_tmn=Decimal(30_000_000),
            gold_mg=1_500,
            updated_at=utcnow(),
        )
        for obs in observations
    }

    finder = OpportunityFinder(SPECS, StrategyLimits())
    result = finder.find(quotes, inventories)

    print(f"  best: {result.best if result.best else 'none'}")
    print(f"  rejections by reason: {result.reason_counts()}\n")


def main() -> None:
    amount_mg = 500

    print("=" * 70)
    print("Cash-Slot Rotation vs pairwise net-edge scanning")
    print("=" * 70)
    print()

    show_executable_prices(SNAPSHOT, amount_mg)
    demonstrate_rotation_trap(SNAPSHOT, amount_mg)
    demonstrate_pairwise(SNAPSHOT, amount_mg)
    demonstrate_finder(SNAPSHOT)

    print("=" * 70)
    print("Two-venue case, both prices measured live on 2026-08-31")
    print("=" * 70)
    print()

    live_only = [o for o in SNAPSHOT if o.source.startswith("live")]
    show_executable_prices(live_only, amount_mg)
    demonstrate_rotation_trap(live_only, amount_mg)
    demonstrate_pairwise(live_only, amount_mg)


if __name__ == "__main__":
    main()
