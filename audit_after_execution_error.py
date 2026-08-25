import ast
import json
from pathlib import Path

from adapters.wallgold.client import WallGoldClient
from adapters.miligold.client import MilliGoldClient


source = Path("./live_bot.py").read_text(
    encoding="utf-8-sig"
)

tree = ast.parse(source)

wall_args = None
milli_args = None

for node in tree.body:

    if not isinstance(node, ast.Assign):
        continue

    names = [
        t.id
        for t in node.targets
        if isinstance(t, ast.Name)
    ]

    if not isinstance(node.value, ast.Call):
        continue

    call = node.value

    if (
        "wallgold" in names
        and isinstance(call.func, ast.Name)
        and call.func.id == "WallGoldClient"
    ):
        wall_args = [
            ast.literal_eval(x)
            for x in call.args
        ]

    if (
        "miligold" in names
        and isinstance(call.func, ast.Name)
        and call.func.id == "MilliGoldClient"
    ):
        milli_args = [
            ast.literal_eval(x)
            for x in call.args
        ]


if wall_args is None:
    raise Exception("WallGold config not found")

if milli_args is None:
    raise Exception("MilliGold config not found")


wall = WallGoldClient(
    wall_args[0]
)

milli = MilliGoldClient(
    milli_args[0],
    milli_args[1],
    milli_args[2]
)

milli.login()


# BEFORE THE REAL EXECUTION
WALL_CASH_BEFORE = 18664387.0
WALL_GOLD_BEFORE = 5.199

MILLI_CASH_BEFORE = 11263249.0
MILLI_GOLD_BEFORE = 0.504


wall_balances = wall.get_balance()

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


milli_gold_data = milli.get_balance()
milli_rial_data = milli.get_rial_balance()

milli_gold = (
    milli_gold_data["data"]
    ["availableMilliBalance"]
    /
    1000
)

milli_cash = (
    milli_rial_data["data"]
    ["availableRialBalance"]
    /
    10
)


print("====================================")
print("CURRENT BALANCES")
print("====================================")

print(
    "WALL CASH =",
    wall_cash
)

print(
    "WALL GOLD =",
    wall_gold
)

print(
    "MILLI CASH =",
    milli_cash
)

print(
    "MILLI GOLD =",
    milli_gold
)


print()
print("====================================")
print("DELTA SINCE BEFORE EXECUTION")
print("====================================")

print(
    "WALL CASH DELTA =",
    wall_cash - WALL_CASH_BEFORE
)

print(
    "WALL GOLD DELTA =",
    wall_gold - WALL_GOLD_BEFORE
)

print(
    "MILLI CASH DELTA =",
    milli_cash - MILLI_CASH_BEFORE
)

print(
    "MILLI GOLD DELTA =",
    milli_gold - MILLI_GOLD_BEFORE
)


print()
print("====================================")
print("LATEST WALLGOLD ORDERS")
print("====================================")

r = wall.session.get(
    wall.BASE_URL + "/api/v1/account/orders",
    timeout=15
)

print(
    "STATUS =",
    r.status_code
)

try:

    data = r.json()

    # ASCII output avoids Windows charmap errors.
    print(
        json.dumps(
            data,
            ensure_ascii=True,
            indent=2
        )[:12000]
    )

except Exception:

    print(
        repr(
            r.text[:5000]
        )
    )


print()
print("READ ONLY - NO TRADE EXECUTED")
