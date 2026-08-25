from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import re

from adapters.goldika.client import GoldikaClient

text = Path("./live_bot.py").read_text(
    encoding="utf-8"
)

m = re.search(
    r'''goldika\s*=\s*GoldikaClient\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']\s*\)''',
    text
)

if not m:
    raise Exception(
        "Goldika credentials not found"
    )

c = GoldikaClient(
    m.group(1),
    m.group(2)
)

with redirect_stdout(StringIO()):
    c.login()

data = c.get_balance()

rial_raw = data["data"]["rial"]["total"]["spendable"]
gold_raw = data["data"]["gold"]["total"]["spendable"]

cash_tmn = rial_raw / 10
gold_grams = gold_raw / 1000

print("RAW RIAL =", rial_raw)
print("RAW GOLD =", gold_raw)
print("CASH TMN =", cash_tmn)
print("GOLD GRAMS =", gold_grams)
