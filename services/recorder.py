"""Records executable prices from every reachable venue into a tick store.

None of the venues publish history, so the only way to learn how often the
cross-venue edge actually clears costs is to start writing it down. Nothing else
in the project can be answered without this data, and every day it is not
running is a day that cannot be recovered.

Runs on the Iranian VPS, since two of the venues are unreachable from abroad.

    python3 -m services.recorder --once          # one sweep, print and exit
    python3 -m services.recorder --interval 5    # poll forever
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sqlite3
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import requests

log = logging.getLogger("recorder")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DB_PATH = Path("~/goldarb/ticks.db").expanduser()


@dataclass(frozen=True)
class Tick:
    """One venue's two-sided price at one instant, in toman per gram."""

    platform: str
    buy: int
    sell: int
    latency_ms: int
    raw: dict


class PriceSource:
    """Fetches and normalises one venue's price."""

    def __init__(
        self,
        name: str,
        url: str,
        parse: Callable[[dict], tuple[int, int]],
        headers: dict | None = None,
        auth_env: str | None = None,
    ):
        self.name = name
        self.url = url
        self.parse = parse
        self.headers = {"Accept": "application/json", "User-Agent": UA, **(headers or {})}
        self.auth_env = auth_env

    def available(self) -> bool:
        """Whether this venue can be polled with what we currently hold."""
        return self.auth_env is None or bool(os.environ.get(self.auth_env))

    def _auth_headers(self) -> dict:
        if self.auth_env is None:
            return self.headers
        return {**self.headers, "Authorization": f"Bearer {os.environ[self.auth_env]}"}

    def fetch(self, session: requests.Session) -> Tick | None:
        started = time.perf_counter()
        try:
            response = session.get(self.url, headers=self._auth_headers(), timeout=(5, 12))
            response.raise_for_status()
            payload = response.json()
            buy, sell = self.parse(payload)
        except Exception as exc:
            # A venue being briefly unreachable is normal here and must not stop
            # the sweep; the gap shows up in the data as a missing row.
            log.warning("%s: %s", self.name, exc)
            return None

        latency_ms = int((time.perf_counter() - started) * 1000)
        if buy <= 0 or sell <= 0:
            log.warning("%s: implausible price buy=%s sell=%s", self.name, buy, sell)
            return None
        return Tick(self.name, buy, sell, latency_ms, payload)


# -- venue-specific normalisation -------------------------------------------
#
# Each venue reports in its own unit. Everything is converted to whole toman per
# gram of 18k gold here, so nothing downstream has to know the difference.


def _melligold(payload: dict) -> tuple[int, int]:
    # Already toman per gram. Quotes one reference price on both sides; its
    # spread lives in the commission, not the quote.
    data = payload["data"]
    return int(data["price_buy"]), int(data["price_sell"])


def _miligold(payload: dict) -> tuple[int, int]:
    # price18 is rial per milligram: x100 gives toman per gram. Also a single
    # reference price.
    price = int(payload["data"]["price18"]) * 100
    return price, price


def _goldika(payload: dict) -> tuple[int, int]:
    # Rial per gram, and the only venue here that genuinely quotes two sides.
    price = payload["data"]["price"]
    return int(price["buy"]) // 10, int(price["sell"]) // 10


def _wallgold(payload: dict) -> tuple[int, int]:
    # Toman per gram. The endpoint takes a side parameter but returns the same
    # number either way, so this too is a single reference price whose spread is
    # carried by the 0.5% otcFeeCoefficient.
    price = int(payload["result"]["price"])
    return price, price


def _talasea(payload: dict) -> tuple[int, int]:
    # Thousand-toman per gram, i.e. toman per milligram. Single reference price,
    # and its fee is 1%, twice what the other venues charge.
    price = int(float(payload["price"])) * 1000
    return price, price


SOURCES = [
    PriceSource(
        "melligold",
        "https://melligold.com/api/v1/exchange/buy-sell-price/?symbol=XAU18",
        _melligold,
        {"Referer": "https://melligold.com/pwa/account"},
    ),
    PriceSource(
        "miligold",
        "https://milli.gold/api/v1/public/milli-price/detail",
        _miligold,
        {"X-Channel": "MILLI", "X-Platform": "PWA", "Referer": "https://milli.gold/"},
    ),
    PriceSource(
        "goldika",
        "https://api.goldika.ir/api/public/price",
        _goldika,
        {
            "X-PLATFORM": "web",
            "Origin": "https://goldika.ir",
            "Referer": "https://goldika.ir/",
        },
    ),
    PriceSource(
        "wallgold",
        "https://api.wallgold.ir/api/v1/account/price"
        "?symbol=GLD_18C_750TMN&side=buy",
        _wallgold,
        auth_env="WALLGOLD_API_KEY",
    ),
    PriceSource(
        "talasea",
        "https://api.talasea.ir/api/market/getGoldPrice",
        _talasea,
        {"Origin": "https://talasea.ir", "Referer": "https://talasea.ir/"},
    ),
]


def active_sources() -> list[PriceSource]:
    """Venues we can actually poll right now.

    A venue missing its credential is skipped with a warning rather than
    silently dropped, so a mistyped key shows up as a gap we can explain instead
    of a venue that quietly stopped being considered.
    """
    active = []
    for source in SOURCES:
        if source.available():
            active.append(source)
        else:
            log.warning("%s: skipped, %s is not set", source.name, source.auth_env)
    return active


SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    id         INTEGER PRIMARY KEY,
    sweep_id   INTEGER NOT NULL,
    ts         REAL    NOT NULL,
    platform   TEXT    NOT NULL,
    buy        INTEGER NOT NULL,
    sell       INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    raw        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ticks_ts       ON ticks(ts);
CREATE INDEX IF NOT EXISTS ticks_sweep    ON ticks(sweep_id);
CREATE INDEX IF NOT EXISTS ticks_platform ON ticks(platform, ts);
"""


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    # WAL keeps the analysis queries from blocking the writer.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def sweep(
    session: requests.Session,
    pool: ThreadPoolExecutor,
    sources: list[PriceSource],
) -> list[Tick]:
    """Fetch every venue at once.

    Concurrency is the point: polling three venues in sequence spreads the
    snapshot over seconds, and a cross-venue spread measured from prices taken
    seconds apart is not a spread, it is an artefact.
    """
    return [t for t in pool.map(lambda s: s.fetch(session), sources) if t is not None]


def store(conn: sqlite3.Connection, sweep_id: int, ts: float, ticks: list[Tick]) -> None:
    conn.executemany(
        "INSERT INTO ticks (sweep_id, ts, platform, buy, sell, latency_ms, raw) "
        "VALUES (?,?,?,?,?,?,?)",
        [
            (sweep_id, ts, t.platform, t.buy, t.sell, t.latency_ms,
             json.dumps(t.raw, ensure_ascii=False))
            for t in ticks
        ],
    )
    conn.commit()


def describe(ticks: list[Tick]) -> str:
    if not ticks:
        return "  (no venue responded)"
    lines = [
        f"  {t.platform:<11} buy={t.buy:>12,}  sell={t.sell:>12,}  {t.latency_ms:>5}ms"
        for t in sorted(ticks, key=lambda t: t.platform)
    ]
    # Raw quote spread only, before fees. Enough to see the shape at a glance;
    # the costed version belongs in analysis, not in the recorder.
    best = max(
        (
            (b.platform, s.platform, s.sell - b.buy)
            for b in ticks
            for s in ticks
            if b.platform != s.platform
        ),
        key=lambda r: r[2],
        default=None,
    )
    if best:
        lines.append(f"  best raw spread: {best[0]} -> {best[1]}  {best[2]:+,} /gram")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between sweeps")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    conn = open_db(args.db)
    session = requests.Session()

    row = conn.execute("SELECT COALESCE(MAX(sweep_id), 0) FROM ticks").fetchone()
    sweep_id = row[0]

    running = True

    def stop(*_):
        nonlocal running
        running = False
        log.info("shutting down after this sweep")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    sources = active_sources()
    log.info(
        "recording %d venues (%s) into %s",
        len(sources),
        ", ".join(s.name for s in sources),
        args.db,
    )

    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        while running:
            started = time.time()
            sweep_id += 1
            ticks = sweep(session, pool, sources)
            store(conn, sweep_id, started, ticks)

            if args.once:
                print(describe(ticks))
                break

            if sweep_id % 60 == 0:
                total = conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0]
                log.info("sweep %d, %d rows stored\n%s", sweep_id, total, describe(ticks))

            time.sleep(max(0.0, args.interval - (time.time() - started)))

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
