import ast
from pathlib import Path

from adapters.miligold.client import MilliGoldClient

source = Path("./live_bot.py").read_text(
    encoding="utf-8-sig"
)

tree = ast.parse(source)

args = None

for node in tree.body:

    if not isinstance(node, ast.Assign):
        continue

    if not any(
        isinstance(t, ast.Name)
        and t.id == "miligold"
        for t in node.targets
    ):
        continue

    call = node.value

    if (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "MilliGoldClient"
        and len(call.args) == 3
    ):
        args = [
            ast.literal_eval(x)
            for x in call.args
        ]
        break


if args is None:
    raise Exception(
        "MilliGoldClient config not found"
    )


c = MilliGoldClient(
    args[0],
    args[1],
    args[2]
)

c.login()

raw_price = c._get_raw_price()

print("RAW PRICE =", raw_price)
print()

amounts = [
    100,
    200,
    500,
    1000,
    2000
]

for milli in amounts:

    print(
        "AMOUNT =",
        milli,
        "MILLI"
    )

    for side in [
        "BUY",
        "SELL"
    ]:

        commission = c.get_commission(
            milli,
            raw_price,
            side
        )

        percent_if_milli = (
            commission
            /
            milli
            *
            100
        )

        print(
            side,
            "COMMISSION =",
            commission,
            "| IF UNIT=MILLI =>",
            round(
                percent_if_milli,
                4
            ),
            "%"
        )

    print()


print("NO TRADE EXECUTED")
