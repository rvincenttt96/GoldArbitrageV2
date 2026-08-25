from datetime import datetime, timezone

from core.models import Quote, Portfolio
from services.opportunity_finder import OpportunityFinder
from services.risk_manager import RiskManager


def q(platform, side, price):
    return Quote(
        platform=platform,
        symbol="GLD_18C_750TMN",
        side=side,
        price=price,
        price_id=0,
        expires_at=datetime.now(),
        ttl=30,
        timestamp=datetime.now()
    )


def p(platform, cash, gold):
    return Portfolio(
        platform=platform,
        actual_cash=cash,
        actual_gold=gold,
        allowed_cash=cash,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )


scan = {
    "quotes": [
        q("miligold", "buy", 20000000),
        q("miligold", "sell", 20000000),

        q("goldika", "buy", 21000000),
        q("goldika", "sell", 20500000),

        q("wallgold", "buy", 21800000),
        q("wallgold", "sell", 22000000),
    ]
}


portfolios = {
    # Best nominal buyer, but almost no cash.
    "miligold": p(
        "miligold",
        518943,
        1.004
    ),

    # Enough cash for ~0.47g, but not 0.5g
    # after Goldika's 1.2% buy fee.
    "goldika": p(
        "goldika",
        10000000,
        0.504
    ),

    "wallgold": p(
        "wallgold",
        29500000,
        4.699
    )
}


finder = OpportunityFinder()

opp = finder.find(
    scan,
    0.5,
    portfolios
)

print("OPPORTUNITY =", opp)

assert opp is not None

assert (
    opp.buy_platform
    !=
    "miligold"
), "FAILED: Milli selected despite insufficient cash"

assert (
    opp.amount
    <=
    0.5
)

buy_portfolio = portfolios[
    opp.buy_platform
]

sell_portfolio = portfolios[
    opp.sell_platform
]

required_cash = (
    opp.buy_price
    *
    opp.amount
    +
    opp.buy_fee
)

print()
print(
    "BUY PLATFORM =",
    opp.buy_platform
)

print(
    "SELL PLATFORM =",
    opp.sell_platform
)

print(
    "AUTO AMOUNT =",
    opp.amount
)

print(
    "REQUIRED CASH =",
    required_cash
)

print(
    "AVAILABLE CASH =",
    buy_portfolio.available_cash()
)

print(
    "AVAILABLE SELL GOLD =",
    sell_portfolio.available_gold()
)

print(
    "NET PROFIT =",
    opp.net_profit
)

print(
    "RISK CHECK =",
    RiskManager().check(
        opp,
        buy_portfolio,
        sell_portfolio
    )
)

assert RiskManager().check(
    opp,
    buy_portfolio,
    sell_portfolio
)

print()
print(
    "INVENTORY-AWARE TEST PASSED"
)
print(
    "NO REAL TRADE EXECUTED"
)
