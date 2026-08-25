import ast
from pathlib import Path

from adapters.miligold.client import MilliGoldClient


source = Path("./live_bot.py").read_text(
    encoding="utf-8-sig"
)

tree = ast.parse(source)

credentials = None

for node in tree.body:

    if not isinstance(node, ast.Assign):
        continue

    if not any(
        isinstance(target, ast.Name)
        and target.id == "miligold"
        for target in node.targets
    ):
        continue

    call = node.value

    if (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "MilliGoldClient"
        and len(call.args) == 3
    ):
        credentials = [
            ast.literal_eval(arg)
            for arg in call.args
        ]
        break


if credentials is None:
    raise Exception(
        "MilliGoldClient config not found in live_bot.py"
    )


client = MilliGoldClient(
    credentials[0],
    credentials[1],
    credentials[2]
)


print("=== LOGIN ===")

login = client.login()

print(
    "LOGIN OK:",
    login.get("code") == 0
)


print()
print("=== GOLD BALANCE ===")

gold_data = client.get_balance()

print(gold_data)


print()
print("=== RIAL BALANCE ===")

rial_data = client.get_rial_balance()

print(rial_data)


print()
print("=== PRICE ===")

raw_price = client._get_raw_price()

quote = client.get_price("buy")

print(
    "RAW PRICE:",
    raw_price
)

print(
    "GRAM PRICE TMN:",
    quote.price
)


print()
print("=== NORMALIZED BALANCES ===")

gold_grams = (
    gold_data["data"]["availableMilliBalance"]
    / 1000
)

cash_tmn = (
    rial_data["data"]["availableRialBalance"]
    / 10
)

print(
    "CASH TMN:",
    cash_tmn
)

print(
    "GOLD GRAMS:",
    gold_grams
)


print()
print("NO TRADE EXECUTED")
