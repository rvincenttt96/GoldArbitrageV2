from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
from datetime import datetime, timezone
import re

from core.registry import ExchangeRegistry
from core.models import Portfolio

from services.scanner import MarketScanner
from services.opportunity_finder import OpportunityFinder
from services.risk_manager import RiskManager

from adapters.wallgold.client import WallGoldClient
from adapters.goldika.client import GoldikaClient
from adapters.miligold.client import MilliGoldClient


# -------------------------------------------------
# Read existing credentials from live_bot.py
# -------------------------------------------------

text = Path("./live_bot.py").read_text(
    encoding="utf-8"
)


wall_match = re.search(
    r'''wallgold\s*=\s*WallGoldClient\(\s*["']([^"']+)["']\s*\)''',
    text,
    re.S
)

goldika_match = re.search(
    r'''goldika\s*=\s*GoldikaClient\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']\s*\)''',
    text,
    re.S
)

milli_match = re.search(
    r'''miligold\s*=\s*MilliGoldClient\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']\s*\)''',
    text,
    re.S
)


if not wall_match:
    raise Exception("WallGold credentials not found")

if not goldika_match:
    raise Exception("Goldika credentials not found")

if not milli_match:
    raise Exception("MilliGold credentials not found")


wallgold = WallGoldClient(
    wall_match.group(1)
)

goldika = GoldikaClient(
    goldika_match.group(1),
    goldika_match.group(2)
)

miligold = MilliGoldClient(
    milli_match.group(1),
    milli_match.group(2),
    milli_match.group(3)
)


# -------------------------------------------------
# Login
# -------------------------------------------------

with redirect_stdout(StringIO()):
    goldika.login()

miligold.login()


# -------------------------------------------------
# Live portfolios
# -------------------------------------------------

def load_wallgold():

    balances = wallgold.get_balance()

    cash = 0
    gold = 0

    for b in balances:

        if b.currency == "TMN":
            cash = b.amount - b.locked_amount

        elif b.currency == "GLD_18C_750":
            gold = b.amount - b.locked_amount

    return Portfolio(
        platform="wallgold",
        actual_cash=cash,
        actual_gold=gold,
        allowed_cash=cash,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )


def load_goldika():

    data = goldika.get_balance()

    rial = (
        data["data"]
        ["rial"]
        ["total"]
        ["spendable"]
    )

    gold_milli = (
        data["data"]
        ["gold"]
        ["total"]
        ["spendable"]
    )

    cash = rial / 10
    gold = gold_milli / 1000

    return Portfolio(
        platform="goldika",
        actual_cash=cash,
        actual_gold=gold,
        allowed_cash=cash,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )


def load_milli():

    gold_data = miligold.get_balance()
    rial_data = miligold.get_rial_balance()

    gold = (
        gold_data["data"]
        ["availableMilliBalance"]
        / 1000
    )

    cash = (
        rial_data["data"]
        ["availableRialBalance"]
        / 10
    )

    return Portfolio(
        platform="miligold",
        actual_cash=cash,
        actual_gold=gold,
        allowed_cash=cash,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )


portfolios = {
    "wallgold": load_wallgold(),
    "goldika": load_goldika(),
    "miligold": load_milli(),
}


# -------------------------------------------------
# Scanner
# -------------------------------------------------

registry = ExchangeRegistry()

registry.add(wallgold)
registry.add(goldika)
registry.add(miligold)

scanner = MarketScanner(
    registry
)

scan = scanner.scan()


print()
print("======================================")
print("LIVE BALANCES")
print("======================================")

for name, p in portfolios.items():

    print(
        name,
        "CASH_TMN=",
        p.available_cash(),
        "GOLD_G=",
        p.available_gold()
    )


print()
print("======================================")
print("LIVE QUOTES")
print("======================================")

for q in scan["quotes"]:

    print(
        q.platform,
        q.side,
        f"{q.price:,}"
    )


# -------------------------------------------------
# Opportunity
# -------------------------------------------------

amount = 0.5

finder = OpportunityFinder()

opportunity = finder.find(
    scan,
    amount
)


print()
print("======================================")
print("BEST OPPORTUNITY")
print("======================================")

print(opportunity)


if opportunity is None:

    print()
    print("NO CROSS-PLATFORM OPPORTUNITY")

else:

    buy_portfolio = portfolios[
        opportunity.buy_platform
    ]

    sell_portfolio = portfolios[
        opportunity.sell_platform
    ]

    risk_ok = RiskManager().check(
        opportunity,
        buy_portfolio,
        sell_portfolio
    )

    print()
    print("BUY PLATFORM =", opportunity.buy_platform)
    print("SELL PLATFORM =", opportunity.sell_platform)
    print("AMOUNT =", opportunity.amount)
    print("BUY PRICE =", opportunity.buy_price)
    print("SELL PRICE =", opportunity.sell_price)
    print("GROSS PROFIT =", opportunity.gross_profit)
    print("BUY FEE =", opportunity.buy_fee)
    print("SELL FEE =", opportunity.sell_fee)
    print("NET PROFIT =", opportunity.net_profit)

    print()
    print("BUY CASH AVAILABLE =", buy_portfolio.available_cash())
    print(
        "BUY COST =",
        opportunity.buy_price
        *
        opportunity.amount
    )

    print(
        "SELL GOLD AVAILABLE =",
        sell_portfolio.available_gold()
    )

    print()
    print("RISK CHECK =", risk_ok)


print()
print("======================================")
print("DRY RUN ONLY - NO TRADE EXECUTED")
print("======================================")
