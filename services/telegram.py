import html
import requests

from telegram_config import (
    TELEGRAM_BASE_URL,
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
)


def send_telegram_message(text):

    url = (
        f"{TELEGRAM_BASE_URL}"
        f"/bot{TELEGRAM_TOKEN}"
        f"/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        },
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    if data.get("ok") is False:
        raise Exception(
            f"Telegram API error: {data}"
        )

    return data


def _fmt(value):

    if value is None:
        return "-"

    return f"{int(round(value)):,}"


def _safe(value):

    return html.escape(
        str(value)
    )


def _get_quote(
    quotes,
    platform,
    side
):

    for q in quotes:

        if (
            q.platform == platform
            and
            q.side == side
        ):
            return q

    raise ValueError(
        f"Quote not found: "
        f"{platform} {side}"
    )


def send_market_report(scan):

    quotes = scan["quotes"]

    wall_buy = _get_quote(
        quotes,
        "wallgold",
        "buy"
    )

    wall_sell = _get_quote(
        quotes,
        "wallgold",
        "sell"
    )

    goldika_buy = _get_quote(
        quotes,
        "goldika",
        "buy"
    )

    goldika_sell = _get_quote(
        quotes,
        "goldika",
        "sell"
    )

    milli_buy = _get_quote(
        quotes,
        "miligold",
        "buy"
    )

    milli_sell = _get_quote(
        quotes,
        "miligold",
        "sell"
    )


    spreads = [
        (
            "WallGold",
            "Goldika",
            goldika_sell.price
            -
            wall_buy.price
        ),
        (
            "Goldika",
            "WallGold",
            wall_sell.price
            -
            goldika_buy.price
        ),
        (
            "WallGold",
            "MilliGold",
            milli_sell.price
            -
            wall_buy.price
        ),
        (
            "MilliGold",
            "WallGold",
            wall_sell.price
            -
            milli_buy.price
        ),
        (
            "Goldika",
            "MilliGold",
            milli_sell.price
            -
            goldika_buy.price
        ),
        (
            "MilliGold",
            "Goldika",
            goldika_sell.price
            -
            milli_buy.price
        ),
    ]


    best = max(
        spreads,
        key=lambda x: x[2]
    )


    if best[2] > 0:

        status = (
            f"Best raw spread: "
            f"BUY {best[0]} / "
            f"SELL {best[1]} "
            f"(+{_fmt(best[2])})"
        )

    else:

        status = (
            "No positive raw spread "
            "right now"
        )


    report_time = (
        scan["timestamp"]
        .strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )


    text = (
        "<b>GOLD MARKET REPORT</b>\n"
        f"<i>{report_time}</i>\n\n"

        "<b>WallGold</b>\n"
        f"Buy: <code>{_fmt(wall_buy.price)}</code>\n"
        f"Sell: <code>{_fmt(wall_sell.price)}</code>\n\n"

        "<b>Goldika</b>\n"
        f"Buy: <code>{_fmt(goldika_buy.price)}</code>\n"
        f"Sell: <code>{_fmt(goldika_sell.price)}</code>\n\n"

        "<b>MilliGold</b>\n"
        f"Buy: <code>{_fmt(milli_buy.price)}</code>\n"
        f"Sell: <code>{_fmt(milli_sell.price)}</code>\n\n"

        "<b>RAW SPREADS - BEFORE FEES</b>\n"
        f"WallGold -> Goldika: "
        f"<code>{_fmt(spreads[0][2])}</code>\n"

        f"Goldika -> WallGold: "
        f"<code>{_fmt(spreads[1][2])}</code>\n"

        f"WallGold -> MilliGold: "
        f"<code>{_fmt(spreads[2][2])}</code>\n"

        f"MilliGold -> WallGold: "
        f"<code>{_fmt(spreads[3][2])}</code>\n"

        f"Goldika -> MilliGold: "
        f"<code>{_fmt(spreads[4][2])}</code>\n"

        f"MilliGold -> Goldika: "
        f"<code>{_fmt(spreads[5][2])}</code>\n\n"

        f"<b>{status}</b>"
    )


    return send_telegram_message(
        text
    )


def send_trade_signal(opportunity):

    text = (
        "<b>ARBITRAGE EXECUTION SIGNAL</b>\n\n"

        f"BUY: "
        f"<b>{_safe(opportunity.buy_platform)}</b>\n"

        f"SELL: "
        f"<b>{_safe(opportunity.sell_platform)}</b>\n"

        f"Amount: "
        f"<code>{opportunity.amount}</code> g\n\n"

        f"Buy price: "
        f"<code>{_fmt(opportunity.buy_price)}</code>\n"

        f"Sell price: "
        f"<code>{_fmt(opportunity.sell_price)}</code>\n\n"

        f"Gross profit: "
        f"<code>{_fmt(opportunity.gross_profit)}</code>\n"

        f"Buy fee: "
        f"<code>{_fmt(opportunity.buy_fee)}</code>\n"

        f"Sell fee: "
        f"<code>{_fmt(opportunity.sell_fee)}</code>\n"

        f"Estimated net: "
        f"<b>{_fmt(opportunity.net_profit)}</b>"
    )

    return send_telegram_message(
        text
    )


def send_trade_result(
    opportunity,
    result
):

    status = result.get(
        "status",
        "unknown"
    )

    route = (
        f"{opportunity.buy_platform}"
        f" -> "
        f"{opportunity.sell_platform}"
    )


    if status == "completed":

        text = (
            "<b>TRADE COMPLETED</b>\n\n"

            f"Route: "
            f"<code>{_safe(route)}</code>\n"

            f"Amount: "
            f"<code>{opportunity.amount}</code> g\n"

            f"Buy price: "
            f"<code>{_fmt(result.get('current_buy_price'))}</code>\n"

            f"Sell price: "
            f"<code>{_fmt(result.get('current_sell_price'))}</code>\n"

            f"Estimated net: "
            f"<b>{_fmt(result.get('estimated_net_profit'))}</b>"
        )


    elif status == "partial_execution":

        text = (
            "<b>CRITICAL: PARTIAL EXECUTION</b>\n\n"

            f"Route: "
            f"<code>{_safe(route)}</code>\n"

            f"Stage: "
            f"<code>{_safe(result.get('stage'))}</code>\n"

            "<b>TRADING HALTED</b>\n\n"

            f"Error: "
            f"<code>{_safe(result.get('error', result.get('reason', '-')))}</code>"
        )


    elif status == "execution_uncertain":

        text = (
            "<b>CRITICAL: EXECUTION UNCERTAIN</b>\n\n"

            f"Route: "
            f"<code>{_safe(route)}</code>\n"

            f"Stage: "
            f"<code>{_safe(result.get('stage'))}</code>\n"

            "<b>TRADING HALTED</b>\n\n"

            f"Error: "
            f"<code>{_safe(result.get('error', '-'))}</code>"
        )


    else:

        text = (
            "<b>TRADE NOT EXECUTED</b>\n\n"

            f"Route: "
            f"<code>{_safe(route)}</code>\n"

            f"Status: "
            f"<code>{_safe(status)}</code>\n"

            f"Reason: "
            f"<code>{_safe(result.get('reason', '-'))}</code>\n"

            f"Estimated net: "
            f"<code>{_fmt(result.get('estimated_net_profit'))}</code>"
        )


    return send_telegram_message(
        text
    )
