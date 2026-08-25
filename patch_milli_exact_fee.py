from pathlib import Path

p = Path("./services/opportunity_finder.py")
s = p.read_text(encoding="utf-8-sig")

old_buy = '''        if platform == "miligold":
            return value * MILLIGOLD_BUY_FEE'''

new_buy = '''        if platform == "miligold":

            milli_amount = int(
                round(amount * 1000)
            )

            commission_milli = int(
                milli_amount
                *
                MILLIGOLD_BUY_FEE
            )

            return (
                commission_milli
                /
                1000
                *
                price
            )'''

old_sell = '''        if platform == "miligold":
            return value * MILLIGOLD_SELL_FEE'''

new_sell = '''        if platform == "miligold":

            milli_amount = int(
                round(amount * 1000)
            )

            commission_milli = int(
                milli_amount
                *
                MILLIGOLD_SELL_FEE
            )

            return (
                commission_milli
                /
                1000
                *
                price
            )'''

if old_buy not in s:
    raise Exception("Milli BUY fee block not found")

if old_sell not in s:
    raise Exception("Milli SELL fee block not found")

s = s.replace(
    old_buy,
    new_buy,
    1
)

s = s.replace(
    old_sell,
    new_sell,
    1
)

p.write_text(
    s,
    encoding="utf-8"
)

print("MILLI EXACT COMMISSION MODEL APPLIED")
