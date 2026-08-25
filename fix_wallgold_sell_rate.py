from pathlib import Path
import re

p = Path("./config/settings.py")
s = p.read_text(encoding="utf-8")

s, n = re.subn(
    r'(?m)^WALLGOLD_SELL_FEE\s*=\s*[0-9.]+\s*$',
    'WALLGOLD_SELL_FEE = 0.005',
    s
)

if n != 1:
    raise Exception(f"WALLGOLD_SELL_FEE replacements: {n}")

p.write_text(s, encoding="utf-8")
print("DONE")
