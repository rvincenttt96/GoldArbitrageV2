import ast
from pathlib import Path
from datetime import datetime, timezone
from contextlib import redirect_stdout
from io import StringIO

from core.registry import ExchangeRegistry
from core.models import Portfolio

from services.scanner import MarketScanner
from services.opportunity_finder import OpportunityFinder
from services.risk_manager import RiskManager

from adapters.wallgold.client import WallGoldClient
from adapters.goldika.client import GoldikaClient
from adapters.miligold.client import MilliGoldClient


source = Path("./live_bot.py").read_text(
    encoding="utf-8-sig"
)

tree = ast.parse(source)

wall_args = None
goldika_args = None
milli_args = None

for node in tree.body:

    if not isinstance(node, ast.Assign):
        continue

    if not isinstance(node.value, ast.Call):
        continue

    names = [
        t.id
        for t in node.targets
        if isinstance(t, ast.Name)
    ]

    call = node.value

    if not isinstance(call.func, ast.Name):
        continue

    if (
        "wallgold" in names
        and call.func.id == "WallGoldClient"
    ):
        wall_args = [
            ast.literal_eval(x)
            for x in call.args
        ]

    elif (
        "goldika" in names
        and call.func.id == "GoldikaClient"
    ):
        goldika_args = [
            ast.literal_eval(x)
            for x in call.args
        ]

    elif (
        "miligold" in names
        and call.func.id == "MilliGoldClient"
    ):
        milli_args = [
            ast.literal_eval(x)
            for x in call.args
        ]


if not all([
    wall_args,
    goldika_args,
    milli_args
]):
    raise Exception(
        "Exchange configuration not found"
    )


wallgold = WallGoldClient(
    wall_args[0]
)

goldika = GoldikaClient(
    goldika_args[0],
    goldika_args[1]
)

miligold = MilliGoldClient(
    milli_args[0],
    milli_args[1],
    milli_args[2]
)


with redirect_stdout(StringIO()):
    goldika.login()

miligold.login()


# -----------------------------
# LIVE PORTFOLIOS
# -----------------------------

wall_balances = wallgold.get_balance()

wall_cash = 0
wall_gold = 0

for b in wall_balances:

    if b.currency == "TMN":
        wall_cash = (
            b.amount
            -
            b.locked_amount
        )

    elif b.currency == "GLD_18C_750":
        wall_gold = (
            b.amount
            -
            b.locked_amount
        )


goldika_data = goldika.get_balance()

goldika_cash = (
    goldika_data["data"]
    ["rial"]["total"]["spendable"]
    /
    10
)

goldika_gold = (
    goldika_data["data"]
    ["gold"]["total"]["spendable"]
    /
    1000
)


milli_gold_data = miligold.get_balance()
milli_cash_data = miligold.get_rial_balance()

milli_gold = (
    milli_gold_data["data"]
    ["availableMilliBalance"]
    /
    1000
)

milli_cash = (
    milli_cash_data["data"]
    ["availableRialBalance"]
    /
    10
)


portfolios = {
    "wallgold": Portfolio(
        platform="wallgold",
        actual_cash=wall_cash,
        actual_gold=wall_gold,
        allowed_cash=wall_cash,
        allowed_gold=wall_gold,
        updated_at=datetime.now(timezone.utc)
    ),

    "goldika": Portfolio(
        platform="goldika",
        actual_cash=goldika_cash,
        actual_gold=goldika_gold,
        allowed_cash=goldika_cash,
        allowed_gold=goldika_gold,
        updated_at=datetime.now(timezone.utc)
    ),

    "miligold": Portfolio(
        platform="miligold",
        actual_cash=milli_cash,
        actual_gold=milli_gold,
        allowed_cash=milli_cash,
        allowed_gold=milli_gold,
        updated_at=datetime.now(timezone.utc)
    )
}


# -----------------------------
# LIVE PRICES
# -----------------------------

registry = ExchangeRegistry()

registry.add(wallgold)
registry.add(goldika)
registry.add(miligold)

scan = MarketScanner(
    registry
).scan()


print()
print("======================================")
print("LIVE PORTFOLIOS")
print("======================================")

for name, p in portfolios.items():

    print(
        name,
        "CASH=",
        p.available_cash(),
        "GOLD=",
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
        q.price
    )


finder = OpportunityFinder()

opportunity = finder.find(
    scan,
    0.5,
    portfolios
)


print()
print("======================================")
print("EXECUTABLE OPPORTUNITY")
print("======================================")

print(opportunity)


if opportunity is not None:

    bp = portfolios[
        opportunity.buy_platform
    ]

    sp = portfolios[
        opportunity.sell_platform
    ]

    required_cash = (
        opportunity.buy_price
        *
        opportunity.amount
        +
        opportunity.buy_fee
    )

    print()
    print(
        "BUY PLATFORM =",
        opportunity.buy_platform
    )

    print(
        "SELL PLATFORM =",
        opportunity.sell_platform
    )

    print(
        "AUTO AMOUNT =",
        opportunity.amount
    )

    print(
        "REQUIRED CASH =",
        required_cash
    )

    print(
        "BUY CASH AVAILABLE =",
        bp.available_cash()
    )

    print(
        "SELL GOLD AVAILABLE =",
        sp.available_gold()
    )

    print(
        "NET PROFIT =",
        opportunity.net_profit
    )

    print(
        "RISK CHECK =",
        RiskManager().check(
            opportunity,
            bp,
            sp
        )
    )


print()
print("======================================")
print("READ ONLY - NO TRADE EXECUTED")
print("======================================")
