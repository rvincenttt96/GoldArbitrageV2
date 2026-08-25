from pathlib import Path

p = Path("./live_bot.py")
s = p.read_text(encoding="utf-8")

old = '''        if b.currency == "TMN":
            cash = b.amount

        if b.currency == "GLD_18C_750":
            gold = b.amount'''

new = '''        if b.currency == "TMN":
            cash = b.amount - b.locked_amount

        if b.currency == "GLD_18C_750":
            gold = b.amount - b.locked_amount'''

if old not in s:
    raise Exception("target not found")

p.write_text(
    s.replace(old, new),
    encoding="utf-8"
)

print("DONE")
