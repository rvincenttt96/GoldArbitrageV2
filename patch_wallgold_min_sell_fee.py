from pathlib import Path

p = Path("./services/opportunity_finder.py")
s = p.read_text(encoding="utf-8")

old = '''        if platform == "wallgold":
            return value * WALLGOLD_SELL_FEE'''

new = '''        if platform == "wallgold":
            billable_amount = max(amount, 0.4)
            return billable_amount * price * WALLGOLD_SELL_FEE'''

if old not in s:
    raise Exception("WallGold sell fee block not found")

p.write_text(
    s.replace(old, new),
    encoding="utf-8"
)

print("DONE")
