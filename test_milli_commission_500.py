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
    raise Exception("MilliGoldClient config not found")

c = MilliGoldClient(
    args[0],
    args[1],
    args[2]
)

c.login()

raw_price = c._get_raw_price()

commission_buy = c.get_commission(
    500,
    raw_price,
    "BUY"
)

commission_sell = c.get_commission(
    500,
    raw_price,
    "SELL"
)

print("RAW PRICE =", raw_price)
print("500 MILLI BUY COMMISSION =", commission_buy)
print("500 MILLI SELL COMMISSION =", commission_sell)
print("NO TRADE EXECUTED")
