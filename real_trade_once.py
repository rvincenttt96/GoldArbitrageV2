import ast
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

from core.registry import ExchangeRegistry
from core.models import Portfolio

from services.scanner import MarketScanner
from services.opportunity_finder import OpportunityFinder
from services.risk_manager import RiskManager
from services.executor import Executor

from adapters.wallgold.client import WallGoldClient
from adapters.goldika.client import GoldikaClient
from adapters.miligold.client import MilliGoldClient

from config.settings import MAX_TRADE_AMOUNT


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="backslashreplace"
    )

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(
        encoding="utf-8",
        errors="backslashreplace"
    )


# =========================================================
# LOAD EXISTING CONFIG
# =========================================================

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


# =========================================================
# CLIENTS
# =========================================================

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


goldika.login()
miligold.login()


# =========================================================
# LIVE PORTFOLIOS
# =========================================================

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


# =========================================================
# MARKET
# =========================================================

registry = ExchangeRegistry()

registry.add(wallgold)
registry.add(goldika)
registry.add(miligold)

scanner = MarketScanner(
    registry
)

finder = OpportunityFinder()

risk_manager = RiskManager()

executor = Executor(
    risk_manager
)


exchanges = {
    "wallgold": wallgold,
    "goldika": goldika,
    "miligold": miligold
}


scan = scanner.scan()


opportunity = finder.find(
    scan,
    MAX_TRADE_AMOUNT,
    portfolios
)


print()
print("======================================")
print("ONE-SHOT REAL TRADE")
print("======================================")

print(
    "OPPORTUNITY =",
    opportunity
)


if opportunity is None:

    print()
    print(
        "NO EXECUTABLE OPPORTUNITY"
    )

    print(
        "NO TRADE EXECUTED"
    )

    raise SystemExit(0)


buy_portfolio = portfolios[
    opportunity.buy_platform
]

sell_portfolio = portfolios[
    opportunity.sell_platform
]


approved = risk_manager.check(
    opportunity,
    buy_portfolio,
    sell_portfolio
)


print(
    "BUY PLATFORM =",
    opportunity.buy_platform
)

print(
    "SELL PLATFORM =",
    opportunity.sell_platform
)

print(
    "AMOUNT =",
    opportunity.amount
)

print(
    "ESTIMATED NET =",
    opportunity.net_profit
)

print(
    "RISK CHECK =",
    approved
)


if not approved:

    print()
    print(
        "RISK REJECTED"
    )

    print(
        "NO TRADE EXECUTED"
    )

    raise SystemExit(0)


buy_exchange = exchanges[
    opportunity.buy_platform
]

sell_exchange = exchanges[
    opportunity.sell_platform
]


print()
print(
    "EXECUTING ONE REAL ARBITRAGE..."
)


result = executor.execute(
    opportunity,
    buy_exchange,
    sell_exchange,
    buy_portfolio,
    sell_portfolio
)


status = result.get(
    "status"
)


print()
print("======================================")
print("EXECUTION RESULT")
print("======================================")

print(
    json.dumps(
        result,
        ensure_ascii=True,
        default=str,
        indent=2
    )
)


if status == "completed":

    print()
    print(
        "ONE-SHOT TRADE COMPLETED"
    )

elif status in {
    "partial_execution",
    "execution_uncertain"
}:

    print()
    print(
        "CRITICAL EXECUTION STATE"
    )

    print(
        "DO NOT RUN ANOTHER TRADE"
    )

else:

    print()
    print(
        "TRADE NOT COMPLETED"
    )


print()
print(
    "ONE-SHOT PROCESS FINISHED"
)
