"""Paper trading against live prices.

Records every signal the strategy produces, whether or not it could have been
acted on, and keeps a virtual book so the strategy's P&L can be read without
risking anything.

Two separate questions get answered per signal, and keeping them apart is the
point of this module:

* Would the strategy have traded? That is the virtual book.
* Could we have traded, with the balances actually sitting on the venues? That
  is the real-inventory check, and a signal that fails it is a funding problem
  rather than a market one.

Prices come from the recorder's tick store rather than fresh calls, so paper and
live see exactly the same market and the venues are polled once, not twice.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal as signal_module
import sqlite3
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from config.loader import load_platforms
from core.models import Inventory, Quote, utcnow
from core.platform import MG_PER_GRAM, PlatformSpec
from services.opportunity_finder import (
    GradedOpportunity,
    OpportunityFinder,
    ScanResult,
    StrategyLimits,
)
from services.telegram import format_market_report, format_trade_signal, send_message
from services.treasury import find_shortfalls, format_alert, plan_transfers

log = logging.getLogger("paper")

TICKS_DB = Path("~/goldarb/ticks.db").expanduser()
PAPER_DB = Path("~/goldarb/paper.db").expanduser()

#: Opening virtual balances, per venue. Deliberately generous so the virtual
#: book measures the strategy rather than the funding, which the real-inventory
#: flag measures separately.
OPENING_CASH_TMN = Decimal(30_000_000)
OPENING_GOLD_MG = 2_000

#: A signal for the same route is not re-logged until this many seconds have
#: passed. Without it a persistent edge writes a row every few seconds and the
#: table stops describing decisions.
SIGNAL_COOLDOWN_SECONDS = 300

#: How often the channel gets a market snapshot even when nothing is tradable.
#: Silence is ambiguous: it looks the same whether the bot is watching a flat
#: market or has quietly died.
MARKET_REPORT_SECONDS = 1800

#: Treasury alerts repeat no more often than this. A balance stays low until
#: somebody moves money, which takes hours, so alerting every loop would train
#: the reader to ignore them.
TREASURY_COOLDOWN_SECONDS = 6 * 3600


SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY,
    ts            REAL    NOT NULL,
    buy_platform  TEXT    NOT NULL,
    sell_platform TEXT    NOT NULL,
    grade         TEXT    NOT NULL,
    amount_mg     INTEGER NOT NULL,
    buy_price     INTEGER NOT NULL,
    sell_price    INTEGER NOT NULL,
    buy_fee       INTEGER NOT NULL,
    sell_fee      INTEGER NOT NULL,
    net_profit    INTEGER NOT NULL,
    return_pct    REAL    NOT NULL,
    paper_filled  INTEGER NOT NULL,
    actionable    INTEGER NOT NULL,
    block_reason  TEXT    NOT NULL DEFAULT '',
    book_value    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS signals_ts ON signals(ts);

CREATE TABLE IF NOT EXISTS book (
    platform TEXT PRIMARY KEY,
    cash_tmn TEXT NOT NULL,
    gold_mg  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS misses (
    id     INTEGER PRIMARY KEY,
    ts     REAL NOT NULL,
    reason TEXT NOT NULL,
    n      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS misses_ts ON misses(ts);
"""


@dataclass
class PaperBook:
    """Virtual balances, one entry per venue."""

    balances: dict[str, tuple[Decimal, int]]

    @classmethod
    def opening(cls, platforms) -> PaperBook:
        return cls({p: (OPENING_CASH_TMN, OPENING_GOLD_MG) for p in platforms})

    def inventories(self) -> dict[str, Inventory]:
        now = utcnow()
        return {
            name: Inventory(name, cash, gold, now)
            for name, (cash, gold) in self.balances.items()
        }

    def can_fill(self, graded: GradedOpportunity) -> bool:
        o = graded.opportunity
        cash, _ = self.balances.get(o.buy_platform, (Decimal(0), 0))
        _, gold = self.balances.get(o.sell_platform, (Decimal(0), 0))
        return cash >= o.required_cash and gold >= o.amount_mg

    def fill(self, graded: GradedOpportunity) -> None:
        """Apply both legs. Gold moves onto the buy venue, cash onto the sell one.

        Note what this does to the balance sheet: repeating one route drains
        cash from the buy venue and gold from the sell venue. That drift, not
        the edge, is what eventually stops the strategy.
        """
        o = graded.opportunity

        cash, gold = self.balances[o.buy_platform]
        self.balances[o.buy_platform] = (cash - o.required_cash, gold + o.amount_mg)

        cash, gold = self.balances[o.sell_platform]
        proceeds = o.sell_value - o.sell_fee
        self.balances[o.sell_platform] = (cash + proceeds, gold - o.amount_mg)

    def value(self, price_tmn_per_gram: Decimal) -> Decimal:
        """Mark the whole book to one price, for a single comparable number."""
        total = Decimal(0)
        for cash, gold in self.balances.values():
            total += cash + Decimal(gold) * price_tmn_per_gram / MG_PER_GRAM
        return total

    def save(self, conn: sqlite3.Connection) -> None:
        conn.executemany(
            "INSERT INTO book (platform, cash_tmn, gold_mg) VALUES (?,?,?) "
            "ON CONFLICT(platform) DO UPDATE SET cash_tmn=excluded.cash_tmn, "
            "gold_mg=excluded.gold_mg",
            [(p, str(c), g) for p, (c, g) in self.balances.items()],
        )
        conn.commit()

    @classmethod
    def load(cls, conn: sqlite3.Connection, platforms) -> PaperBook:
        rows = conn.execute("SELECT platform, cash_tmn, gold_mg FROM book").fetchall()
        if not rows:
            return cls.opening(platforms)
        balances = {p: (Decimal(c), g) for p, c, g in rows}
        for p in platforms:
            balances.setdefault(p, (OPENING_CASH_TMN, OPENING_GOLD_MG))
        return cls(balances)


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def latest_quotes(
    ticks: sqlite3.Connection, specs: dict[str, PlatformSpec]
) -> tuple[float, list[Quote]]:
    """Quotes from the newest complete sweep in the tick store."""
    row = ticks.execute("SELECT MAX(sweep_id) FROM ticks").fetchone()
    if not row or row[0] is None:
        return 0.0, []

    rows = ticks.execute(
        "SELECT ts, platform, buy, sell FROM ticks WHERE sweep_id = ?", (row[0],)
    ).fetchall()

    quotes: list[Quote] = []
    ts = 0.0
    for tick_ts, platform, buy, sell in rows:
        if platform not in specs:
            continue
        ts = max(ts, tick_ts)
        stamp = utcnow()
        for side, price in (("buy", buy), ("sell", sell)):
            quotes.append(
                Quote(
                    platform=platform,
                    symbol="GLD_18C_750TMN",
                    side=side,
                    price_tmn_per_gram=Decimal(price),
                    timestamp=stamp,
                )
            )
    return ts, quotes


def real_inventory_blocks(
    graded: GradedOpportunity, real: dict[str, Inventory] | None
) -> str:
    """Why the real balances could not have taken this trade, or ''.

    Reported alongside every signal. A strategy that keeps finding edges it
    cannot fund has a treasury problem, and that looks nothing like a strategy
    that finds no edges at all.
    """
    if real is None:
        return ""

    o = graded.opportunity
    buy = real.get(o.buy_platform)
    sell = real.get(o.sell_platform)

    if buy is None or sell is None:
        return "no live balance for one leg"
    if buy.available_cash < o.required_cash:
        short = o.required_cash - buy.available_cash
        return f"{o.buy_platform} short {short:,.0f} TMN"
    if sell.available_gold_mg < o.amount_mg:
        short = o.amount_mg - sell.available_gold_mg
        return f"{o.sell_platform} short {short}mg gold"
    return ""


class PaperTrader:
    def __init__(
        self,
        specs: dict[str, PlatformSpec],
        paper: sqlite3.Connection,
        ticks: sqlite3.Connection,
        limits: StrategyLimits | None = None,
    ):
        self.specs = specs
        self.paper = paper
        self.ticks = ticks
        self.finder = OpportunityFinder(specs, limits or StrategyLimits())
        self.book = PaperBook.load(paper, specs)
        self.last_quotes: list[Quote] = []
        self._last_logged: dict[tuple[str, str], float] = {}

    def step(
        self, real: dict[str, Inventory] | None = None
    ) -> tuple[GradedOpportunity | None, ScanResult, str]:
        """One scan. Returns the signal, the full result, and any funding block."""
        ts, quotes = latest_quotes(self.ticks, self.specs)
        self.last_quotes = quotes
        if not quotes:
            return None, ScanResult(None, []), ""

        result = self.finder.find(quotes, self.book.inventories())
        self._record_misses(ts, result)

        graded = result.best
        if graded is None:
            return None, result, ""

        route = (graded.opportunity.buy_platform, graded.opportunity.sell_platform)
        if ts - self._last_logged.get(route, 0.0) < SIGNAL_COOLDOWN_SECONDS:
            return None, result, ""
        self._last_logged[route] = ts

        block = real_inventory_blocks(graded, real)
        filled = self.book.can_fill(graded)
        if filled:
            self.book.fill(graded)
            self.book.save(self.paper)

        self._record_signal(ts, graded, filled, block, quotes)
        return graded, result, block

    def _record_signal(self, ts, graded, filled, block, quotes) -> None:
        o = graded.opportunity
        mark = max(q.price_tmn_per_gram for q in quotes)
        self.paper.execute(
            "INSERT INTO signals (ts, buy_platform, sell_platform, grade, amount_mg,"
            " buy_price, sell_price, buy_fee, sell_fee, net_profit, return_pct,"
            " paper_filled, actionable, block_reason, book_value)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ts, o.buy_platform, o.sell_platform, graded.grade.name, o.amount_mg,
                int(o.buy_price), int(o.sell_price), int(o.buy_fee), int(o.sell_fee),
                int(o.net_profit), float(o.return_fraction * 100),
                int(filled), int(not block), block, int(self.book.value(mark)),
            ),
        )
        self.paper.commit()

    def _record_misses(self, ts: float, result: ScanResult) -> None:
        counts = result.reason_counts()
        if not counts:
            return
        self.paper.executemany(
            "INSERT INTO misses (ts, reason, n) VALUES (?,?,?)",
            [(ts, reason, n) for reason, n in counts.items()],
        )
        self.paper.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks-db", type=Path, default=TICKS_DB)
    parser.add_argument("--paper-db", type=Path, default=PAPER_DB)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--telegram", action="store_true", help="announce signals")
    parser.add_argument(
        "--report-interval",
        type=float,
        default=MARKET_REPORT_SECONDS,
        help="seconds between market snapshots posted to the channel; 0 disables",
    )
    parser.add_argument(
        "--balances",
        type=Path,
        help="JSON of live balances, refreshed by scripts/fetch_balances.py; "
             "enables the real-inventory check and treasury alerts",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    specs = {n: s for n, s in load_platforms().items() if s.enabled}
    paper = open_db(args.paper_db)
    ticks = sqlite3.connect(f"file:{args.ticks_db}?mode=ro", uri=True, timeout=30)
    trader = PaperTrader(specs, paper, ticks)

    log.info("paper trading %d venues: %s", len(specs), ", ".join(sorted(specs)))

    watcher = TreasuryWatcher(specs, announce=args.telegram)
    last_report = 0.0
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal_module.signal(signal_module.SIGTERM, stop)
    signal_module.signal(signal_module.SIGINT, stop)

    while running:
        started = time.time()
        try:
            real = load_balances(args.balances) if args.balances else None
            if real:
                watcher.check(real)
            graded, result, block = trader.step(real)
            if graded is not None:
                log.info(
                    "SIGNAL %s%s", graded,
                    f"  [not actionable: {block}]" if block else "  [actionable]",
                )
                if args.telegram:
                    _announce(graded, block)
            elif args.once:
                log.info("no signal; reasons: %s", json.dumps(result.reason_counts()))

            if (
                args.telegram
                and args.report_interval > 0
                and trader.last_quotes
                and time.time() - last_report >= args.report_interval
            ):
                last_report = time.time()
                _post_market_report(specs, trader.last_quotes)
        except Exception:
            log.exception("paper step failed")

        if args.once:
            break
        time.sleep(max(0.0, args.interval - (time.time() - started)))

    paper.close()
    ticks.close()
    return 0


def load_balances(path: Path) -> dict[str, Inventory] | None:
    """Live balances written by the balance fetcher, or None if unavailable.

    Read from a file rather than fetched here so that a venue being slow or
    logged out cannot stall the scan loop.
    """
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        log.warning("no usable balances at %s", path)
        return None

    now = utcnow()
    return {
        name: Inventory(name, Decimal(str(v["cash_tmn"])), int(v["gold_mg"]), now)
        for name, v in raw.items()
    }


class TreasuryWatcher:
    """Alerts when a venue can no longer fund its side of a trade."""

    def __init__(self, specs: dict[str, PlatformSpec], announce: bool = False):
        self.specs = specs
        self.announce = announce
        self._last_sent = 0.0
        self._last_signature: tuple = ()

    def check(self, inventories: dict[str, Inventory]) -> str:
        shortfalls = find_shortfalls(self.specs, inventories)
        if not shortfalls:
            self._last_signature = ()
            return ""

        text = format_alert(shortfalls, plan_transfers(self.specs, inventories, shortfalls))

        # Re-send early when a *new* venue drops below its line; otherwise wait
        # out the cooldown so a standing shortfall does not become background
        # noise the reader stops seeing.
        signature = tuple(sorted((s.platform, str(s.asset)) for s in shortfalls))
        changed = signature != self._last_signature
        due = time.time() - self._last_sent >= TREASURY_COOLDOWN_SECONDS

        if self.announce and (changed or due):
            try:
                send_message(text)
                self._last_sent = time.time()
                self._last_signature = signature
            except Exception:
                log.exception("treasury alert failed to send")

        return text


def _post_market_report(specs: dict[str, PlatformSpec], quotes: list[Quote]) -> None:
    try:
        send_message(format_market_report(quotes, specs))
        log.info("posted market report")
    except Exception:
        log.exception("market report failed to send")


def _announce(graded: GradedOpportunity, block: str) -> None:
    text = format_trade_signal(graded)
    if block:
        text += (
            "\n\n<b>NOT ACTIONABLE</b>\n"
            f"<code>{block}</code>\n"
            "<i>Signal recorded on paper only.</i>"
        )
    else:
        text += "\n\n<i>Paper trade recorded.</i>"

    try:
        send_message(text)
    except Exception:
        log.exception("telegram announce failed")


if __name__ == "__main__":
    raise SystemExit(main())
