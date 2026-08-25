from pathlib import Path
import re

p = Path("./config/settings.py")
s = p.read_text(encoding="utf-8")

values = {
    "GOLDIKA_BUY_FEE": "0.012",
    "GOLDIKA_SELL_FEE": "0.012",
    "GOLDIKA_BUY_ENABLED": "False",
}

for name, value in values.items():

    pattern = rf"(?m)^{name}\s*=.*$"

    if re.search(pattern, s):
        s = re.sub(
            pattern,
            f"{name} = {value}",
            s
        )
    else:
        if not s.endswith("\n"):
            s += "\n"

        s += f"{name} = {value}\n"

p.write_text(
    s,
    encoding="utf-8"
)

print("SETTINGS DONE")
