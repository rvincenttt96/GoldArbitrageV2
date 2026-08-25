from pathlib import Path

p = Path("./live_bot.py")
s = p.read_text(encoding="utf-8")

old = '''def load_goldika_portfolio():

    return Portfolio(
        platform="goldika",
        actual_cash=10000000,
        actual_gold=0.45,
        allowed_cash=10000000,
        allowed_gold=0.45,
        updated_at=datetime.now(timezone.utc)
    )'''

new = '''def load_goldika_portfolio():

    data = goldika.get_balance()

    rial = data["data"]["rial"]["total"]["spendable"]
    gold_milli = data["data"]["gold"]["total"]["spendable"]

    cash = rial / 10
    gold = gold_milli / 1000

    return Portfolio(
        platform="goldika",
        actual_cash=cash,
        actual_gold=gold,
        allowed_cash=cash,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )'''

if old not in s:
    raise Exception("Goldika portfolio block not found")

p.write_text(
    s.replace(old, new, 1),
    encoding="utf-8"
)

print("GOLDIKA LIVE PORTFOLIO DONE")
