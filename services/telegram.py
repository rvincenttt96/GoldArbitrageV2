"""Telegram reporting.

Nothing here names a venue. The report renders whatever the scanner returned, so
adding a platform changes the config and nothing else.

It also reports all-in prices rather than raw quotes. Most of these venues
publish a single reference price and carry their spread in the commission, so a
table of raw quotes invites a comparison that is not true: a venue can look
cheapest and still be the most expensive to trade on.
"""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from decimal import Decimal

import requests

from core.fees import fee_tmn
from core.models import Quote
from core.platform import MG_PER_GRAM, PlatformSpec
from services.opportunity_finder import GradedOpportunity, ScanResult

BASE_URL = os.environ.get(
    "TELEGRAM_BASE_URL", "https://gold-arbitrage.gold-arbitrage.workers.dev"
)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

#: Size the report prices at. Minimum billable weights mean the ranking at one
#: size is not the ranking at another, so the report has to name the size it is
#: talking about.
REPORT_SIZE_MG = 500

#: Routes listed in the market report. Enough to see where the market is without
#: turning the message into a wall that nobody reads.
TOP_ROUTES = 5


class TelegramError(RuntimeError):
    pass


def send_message(text: str) -> dict:
    if not TOKEN or not CHAT_ID:
        raise TelegramError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID are not set")

    response = requests.post(
        f"{BASE_URL}/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("ok") is False:
        raise TelegramError(f"Telegram rejected the message: {payload}")
    return payload


# -- formatting -------------------------------------------------------------


def _n(value) -> str:
    if value is None:
        return "-"
    return f"{round(float(value)):,}"


def _esc(value) -> str:
    return html.escape(str(value))


def _grams(amount_mg: int) -> str:
    return f"{Decimal(amount_mg) / MG_PER_GRAM:.3f}g"


@dataclass(frozen=True)
class VenueLine:
    """One venue's all-in prices at the report size."""

    spec: PlatformSpec
    net_buy: Decimal
    net_sell: Decimal

    @property
    def round_trip(self) -> Decimal:
        return self.net_buy - self.net_sell


def venue_lines(
    quotes: list[Quote],
    specs: dict[str, PlatformSpec],
    size_mg: int = REPORT_SIZE_MG,
) -> list[VenueLine]:
    """All-in buy and sell price per gram for every venue that answered.

    Venues missing from the scan are simply absent. One venue being unreachable
    must not cost us the report on the others.
    """
    by_platform: dict[str, dict[str, Quote]] = {}
    for quote in quotes:
        by_platform.setdefault(quote.platform, {})[quote.side] = quote

    per_gram = Decimal(MG_PER_GRAM) / size_mg
    lines = []
    for platform, sides in by_platform.items():
        spec = specs.get(platform)
        buy, sell = sides.get("buy"), sides.get("sell")
        if spec is None or buy is None or sell is None:
            continue

        bp, sp = buy.price_tmn_per_gram, sell.price_tmn_per_gram
        lines.append(
            VenueLine(
                spec=spec,
                net_buy=bp + fee_tmn(spec.buy_fee, size_mg, bp) * per_gram,
                net_sell=sp - fee_tmn(spec.sell_fee, size_mg, sp) * per_gram,
            )
        )

    return sorted(lines, key=lambda line: line.round_trip)


def route_edges(lines: list[VenueLine]) -> list[tuple[str, str, Decimal]]:
    """Net edge per gram for every ordered pair, best first."""
    edges = [
        (buy.spec.display_name, sell.spec.display_name, sell.net_sell - buy.net_buy)
        for buy in lines
        for sell in lines
        if buy.spec.name != sell.spec.name
    ]
    return sorted(edges, key=lambda row: row[2], reverse=True)


# -- messages ---------------------------------------------------------------


def format_market_report(
    quotes: list[Quote],
    specs: dict[str, PlatformSpec],
    size_mg: int = REPORT_SIZE_MG,
    timestamp=None,
) -> str:
    lines = venue_lines(quotes, specs, size_mg)
    if not lines:
        return "<b>GOLD MARKET REPORT</b>\n\nNo venue returned a usable price."

    when = (timestamp or quotes[0].timestamp).strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        "<b>GOLD MARKET REPORT</b>",
        f"<i>{_esc(when)} UTC · sized at {_grams(size_mg)}</i>",
        "",
        "<b>ALL-IN PRICES</b> <i>(after fees)</i>",
    ]

    for line in lines:
        mark = "" if line.spec.tradable else " <i>(scan only)</i>"
        parts.append(
            f"<b>{_esc(line.spec.display_name)}</b>{mark}\n"
            f"  buy <code>{_n(line.net_buy)}</code>  "
            f"sell <code>{_n(line.net_sell)}</code>  "
            f"cost <code>{_n(line.round_trip)}</code>"
        )

    parts.append("")
    parts.append("<b>BEST ROUTES</b> <i>(net, per gram)</i>")

    edges = route_edges(lines)
    for buy_name, sell_name, edge in edges[:TOP_ROUTES]:
        sign = "+" if edge > 0 else ""
        parts.append(
            f"  {_esc(buy_name)} → {_esc(sell_name)}: "
            f"<code>{sign}{_n(edge)}</code>"
        )

    best = edges[0] if edges else None
    parts.append("")
    if best and best[2] > 0:
        parts.append(
            f"<b>Best: {_esc(best[0])} → {_esc(best[1])} "
            f"at +{_n(best[2])}/gram</b>"
        )
    else:
        # Saying how far short we are is more use than saying there is nothing.
        shortfall = f" (short by {_n(-best[2])}/gram)" if best else ""
        parts.append(f"<b>No profitable route{shortfall}</b>")

    return "\n".join(parts)


def format_scan_summary(result: ScanResult) -> str:
    """Why nothing traded, grouped by reason.

    The distribution of reasons separates "there was no edge" from "there was an
    edge we could not act on", and those call for opposite fixes.
    """
    counts = result.reason_counts()
    if not counts:
        return ""
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])
    body = "\n".join(f"  {_esc(reason)}: <code>{n}</code>" for reason, n in ordered)
    return f"<b>REJECTED</b>\n{body}"


def format_trade_signal(graded: GradedOpportunity) -> str:
    opportunity = graded.opportunity
    return "\n".join([
        f"<b>SIGNAL · GRADE {_esc(graded.grade.name)}</b>",
        "",
        f"Route: <b>{_esc(opportunity.buy_platform)} → "
        f"{_esc(opportunity.sell_platform)}</b>",
        f"Size: <code>{_grams(opportunity.amount_mg)}</code> "
        f"<i>({_n(graded.grade.capital_fraction * 100)}% allowance)</i>",
        "",
        f"Buy  <code>{_n(opportunity.buy_price)}</code>  "
        f"fee <code>{_n(opportunity.buy_fee)}</code>",
        f"Sell <code>{_n(opportunity.sell_price)}</code>  "
        f"fee <code>{_n(opportunity.sell_fee)}</code>",
        "",
        f"Net: <b>{_n(opportunity.net_profit)}</b> "
        f"({opportunity.return_fraction * 100:.3f}%)",
    ])


def format_trade_result(graded: GradedOpportunity, result: dict) -> str:
    opportunity = graded.opportunity
    status = str(result.get("status", "unknown"))
    route = f"{opportunity.buy_platform} → {opportunity.sell_platform}"

    headers = {
        "completed": "<b>TRADE COMPLETED</b>",
        "partial_execution": "<b>CRITICAL · PARTIAL EXECUTION</b>",
        "execution_uncertain": "<b>CRITICAL · EXECUTION UNCERTAIN</b>",
    }
    parts = [headers.get(status, "<b>TRADE NOT EXECUTED</b>"), ""]
    parts.append(f"Route: <code>{_esc(route)}</code>")
    parts.append(f"Size: <code>{_grams(opportunity.amount_mg)}</code>")
    parts.append(f"Grade: <code>{_esc(graded.grade.name)}</code>")

    if status == "completed":
        parts += [
            f"Buy  <code>{_n(result.get('current_buy_price'))}</code>",
            f"Sell <code>{_n(result.get('current_sell_price'))}</code>",
            "",
            f"Estimated net: <b>{_n(result.get('estimated_net_profit'))}</b>",
        ]
    elif status in {"partial_execution", "execution_uncertain"}:
        parts += [
            f"Stage: <code>{_esc(result.get('stage'))}</code>",
            "",
            "<b>TRADING HALTED — needs a human</b>",
            f"<code>{_esc(result.get('error', result.get('reason', '-')))}</code>",
        ]
    else:
        parts += [
            f"Status: <code>{_esc(status)}</code>",
            f"Reason: <code>{_esc(result.get('reason', '-'))}</code>",
        ]

    return "\n".join(parts)


# -- send helpers -----------------------------------------------------------


def send_market_report(quotes, specs, size_mg: int = REPORT_SIZE_MG) -> dict:
    return send_message(format_market_report(quotes, specs, size_mg))


def send_trade_signal(graded: GradedOpportunity) -> dict:
    return send_message(format_trade_signal(graded))


def send_trade_result(graded: GradedOpportunity, result: dict) -> dict:
    return send_message(format_trade_result(graded, result))
