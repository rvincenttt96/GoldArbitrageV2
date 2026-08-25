from pathlib import Path

p = Path("./live_bot.py")

s = p.read_text(encoding="utf-8")

old = """def load_miligold_portfolio():

    data = miligold.get_balance()

    milli = data["data"]["availableMilliBalance"]

    gold = milli / 1000


    return Portfolio(
        platform="miligold",
        actual_cash=0,
        actual_gold=gold,
        allowed_cash=0,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )
"""

new = """def load_miligold_portfolio():

    gold_data = miligold.get_balance()
    rial_data = miligold.get_rial_balance()

    milli = gold_data["data"]["availableMilliBalance"]
    rial = rial_data["data"]["availableRialBalance"]

    gold = milli / 1000


    return Portfolio(
        platform="miligold",
        actual_cash=rial,
        actual_gold=gold,
        allowed_cash=rial,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )
"""

if old not in s:
    raise Exception("target block not found")

p.write_text(
    s.replace(old,new),
    encoding="utf-8"
)

print("DONE")
