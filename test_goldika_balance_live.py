from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import json
import re

from adapters.goldika.client import GoldikaClient

text = Path("./live_bot.py").read_text(encoding="utf-8")

m = re.search(
    r'''goldika\s*=\s*GoldikaClient\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']\s*\)''',
    text
)

if not m:
    raise Exception("Goldika credentials not found in live_bot.py")

c = GoldikaClient(
    m.group(1),
    m.group(2)
)

with redirect_stdout(StringIO()):
    c.login()

r = c.session.get(
    c.BASE_URL + "/api/v1/balances/get",
    timeout=15
)

print("STATUS:", r.status_code)

try:
    print(
        json.dumps(
            r.json(),
            ensure_ascii=False,
            indent=2
        )
    )
except Exception:
    print(r.text)
