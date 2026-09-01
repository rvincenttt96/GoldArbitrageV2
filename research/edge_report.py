"""How often the cross-venue edge actually clears costs, and for how long.

Reads the recorder's tick store and answers the question the whole project rests
on: is there a tradable edge, is it structural or episodic, and how many times a
day could it realistically be acted on.

Costs come from the same `FeeSpec` objects the live strategy uses, so a change
to a venue's fee schedule moves this report and production together.

    python3 -m research.edge_report --db ~/goldarb/ticks.db
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from config.loader import load_platforms
from core.fees import fee_tmn
from core.platform import MG_PER_GRAM

#: Size the report is run at. Both WallGold and MelliGold bill a minimum weight,
#: so the economics at 500 mg are not the economics at 100 mg.
SIZE_MG = 500


@dataclass
class Episode:
    """A contiguous run of sweeps where one route stayed above the threshold."""

    route: tuple[str, str]
    start: float
    end: float
    peak_edge: Decimal
    sweeps: int

    @property
    def seconds(self) -> float:
        return self.end - self.start


def load_sweeps(db: Path) -> list[tuple[float, dict[str, tuple[int, int]]]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT sweep_id, ts, platform, buy, sell FROM ticks ORDER BY sweep_id"
    ).fetchall()
    conn.close()

    grouped: dict[int, dict] = defaultdict(dict)
    times: dict[int, float] = {}
    for sweep_id, ts, platform, buy, sell in rows:
        grouped[sweep_id][platform] = (buy, sell)
        times[sweep_id] = ts

    return [(times[s], grouped[s]) for s in sorted(grouped)]


def net_prices(specs, quotes: dict, size_mg: int) -> dict[str, tuple[Decimal, Decimal]]:
    """All-in buy and sell price per gram for every venue in this sweep."""
    out = {}
    per_gram = Decimal(MG_PER_GRAM) / size_mg
    for platform, (buy, sell) in quotes.items():
        spec = specs.get(platform)
        if spec is None:
            continue
        buy_p, sell_p = Decimal(buy), Decimal(sell)
        out[platform] = (
            buy_p + fee_tmn(spec.buy_fee, size_mg, buy_p) * per_gram,
            sell_p - fee_tmn(spec.sell_fee, size_mg, sell_p) * per_gram,
        )
    return out


def report_costs(specs, sweeps, size_mg: int) -> None:
    """What it costs to touch each venue, before any cross-venue comparison."""
    print("Round-trip cost of touching each venue, averaged over the window")
    print(f"  {'venue':<11} {'NetBuy':>14} {'NetSell':>14} {'round-trip':>12} {'as %':>8}")
    print("  " + "-" * 64)

    totals: dict[str, list] = defaultdict(list)
    for _, quotes in sweeps:
        for platform, pair in net_prices(specs, quotes, size_mg).items():
            totals[platform].append(pair)

    for platform in sorted(totals):
        rows = totals[platform]
        nb = sum(r[0] for r in rows) / len(rows)
        ns = sum(r[1] for r in rows) / len(rows)
        print(
            f"  {platform:<11} {nb:>14,.0f} {ns:>14,.0f} "
            f"{nb - ns:>12,.0f} {(nb - ns) / nb * 100:>7.2f}%"
        )


def collect_routes(specs, sweeps, size_mg: int, threshold_pct: Decimal):
    """Edge series per route, plus the runs where it stayed tradable."""
    per_route: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    open_run: dict[tuple[str, str], Episode] = {}
    episodes: list[Episode] = []

    for ts, quotes in sweeps:
        nets = net_prices(specs, quotes, size_mg)
        for buy_v, (nb, _) in nets.items():
            for sell_v, (_, ns) in nets.items():
                if buy_v == sell_v:
                    continue
                route = (buy_v, sell_v)
                edge = ns - nb
                per_route[route].append(edge)

                run = open_run.get(route)
                if edge / nb * 100 >= threshold_pct:
                    if run is None:
                        open_run[route] = Episode(route, ts, ts, edge, 1)
                    else:
                        run.end = ts
                        run.sweeps += 1
                        run.peak_edge = max(run.peak_edge, edge)
                elif run is not None:
                    episodes.append(run)
                    del open_run[route]

    episodes.extend(open_run.values())
    return per_route, episodes


def report_routes(per_route, episodes) -> list:
    print("\nEdge per route, in toman per gram")
    print(f"  {'route':<24} {'median':>12} {'best':>12} {'% of time tradable':>20}")
    print("  " + "-" * 72)

    ranked = sorted(per_route.items(), key=lambda kv: -sorted(kv[1])[len(kv[1]) // 2])
    for route, edges in ranked:
        ordered = sorted(edges)
        live = sum(e.sweeps for e in episodes if e.route == route)
        share = live / len(edges) * 100 if edges else 0
        print(
            f"  {route[0] + ' -> ' + route[1]:<24} "
            f"{ordered[len(ordered) // 2]:>12,.0f} {ordered[-1]:>12,.0f} {share:>19.1f}%"
        )
    return ranked


def report_episodes(episodes, span_hours: float, threshold_pct: Decimal) -> None:
    """Whether the edge arrives in bursts or simply sits there.

    The distinction decides the whole design: bursts call for latency, a
    permanent gap calls for capital throughput.
    """
    print(f"\nEpisodes above {threshold_pct}% (contiguous runs)")
    if not episodes:
        print("  none")
        return

    by_route: dict[tuple[str, str], list[Episode]] = defaultdict(list)
    for e in episodes:
        by_route[e.route].append(e)

    print(f"  {'route':<24} {'episodes':>9} {'per day':>9} {'median len':>12} {'longest':>10}")
    print("  " + "-" * 68)
    for route, eps in sorted(by_route.items(), key=lambda kv: -len(kv[1])):
        lengths = sorted(e.seconds for e in eps)
        print(
            f"  {route[0] + ' -> ' + route[1]:<24} {len(eps):>9} "
            f"{len(eps) / (span_hours / 24):>9.1f} "
            f"{lengths[len(lengths) // 2]:>11.0f}s {lengths[-1]:>9.0f}s"
        )


def report_percentiles(specs, sweeps, size_mg: int) -> None:
    """Return distribution per route, as a percentage of the cash deployed.

    A median tells you nothing about whether the tail is tradable, and a
    strategy that only fires on the good tail lives or dies on that tail.
    """
    print("\nNet return distribution, % of notional")
    print(f"  {'route':<24} {'p1':>8} {'p10':>8} {'p50':>8} {'p90':>8} {'p99':>8} {'max':>8}")
    print("  " + "-" * 74)

    series: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    for _, quotes in sweeps:
        nets = net_prices(specs, quotes, size_mg)
        for buy_v, (nb, _) in nets.items():
            for sell_v, (_, ns) in nets.items():
                if buy_v != sell_v and nb > 0:
                    series[(buy_v, sell_v)].append((ns - nb) / nb * 100)

    def pct(values, q):
        return values[min(len(values) - 1, int(len(values) * q))]

    for route, values in sorted(series.items(), key=lambda kv: -sorted(kv[1])[-1]):
        v = sorted(values)
        print(
            f"  {route[0] + ' -> ' + route[1]:<24} "
            f"{pct(v, 0.01):>7.3f}% {pct(v, 0.10):>7.3f}% {pct(v, 0.50):>7.3f}% "
            f"{pct(v, 0.90):>7.3f}% {pct(v, 0.99):>7.3f}% {v[-1]:>7.3f}%"
        )


def report_best(ranked, per_route, size_mg: int) -> None:
    route = ranked[0][0]
    edges = per_route[route]
    positive = [e for e in edges if e > 0]

    print(f"\nBest route: {route[0]} -> {route[1]}")
    print(f"  positive on {len(positive) / len(edges) * 100:.1f}% of sweeps")
    if not positive:
        return

    median = sorted(positive)[len(positive) // 2]
    gram = Decimal(size_mg) / MG_PER_GRAM
    print(f"  median edge when positive: {median:,.0f}/gram")
    print(f"  that is {median * gram:,.0f} toman on a {size_mg}mg ticket")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("~/goldarb/ticks.db").expanduser())
    parser.add_argument("--size-mg", type=int, default=SIZE_MG)
    parser.add_argument(
        "--exclude",
        default="",
        help="comma-separated venues to leave out, e.g. a venue whose quote is "
             "not believed to be executable",
    )
    parser.add_argument(
        "--percentiles",
        action="store_true",
        help="show the return distribution per route instead of just the median",
    )
    parser.add_argument(
        "--threshold-pct",
        type=Decimal,
        default=Decimal("0.4"),
        help="minimum net return, in percent of notional, to count as tradable",
    )
    args = parser.parse_args()

    specs = load_platforms()
    for name in filter(None, (n.strip() for n in args.exclude.split(","))):
        specs.pop(name, None)
    sweeps = load_sweeps(args.db)
    if not sweeps:
        print("no data")
        return 1

    span_hours = (sweeps[-1][0] - sweeps[0][0]) / 3600
    print(f"{len(sweeps):,} sweeps over {span_hours:.1f} hours, sized at {args.size_mg} mg")
    print(f"tradable means net return >= {args.threshold_pct}% of notional\n")

    report_costs(specs, sweeps, args.size_mg)
    per_route, episodes = collect_routes(specs, sweeps, args.size_mg, args.threshold_pct)
    ranked = report_routes(per_route, episodes)
    report_episodes(episodes, span_hours, args.threshold_pct)
    if args.percentiles:
        report_percentiles(specs, sweeps, args.size_mg)
    report_best(ranked, per_route, args.size_mg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
