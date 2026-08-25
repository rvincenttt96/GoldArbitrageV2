from pathlib import Path
import re
import io
from contextlib import redirect_stdout

from adapters.goldika.client import GoldikaClient

text = Path("./live_bot.py").read_text(encoding="utf-8")

m = re.search(
    r'''goldika\s*=\s*GoldikaClient\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']\s*\)''',
    text
)

if not m:
    raise Exception("Goldika credentials not found in live_bot.py")

username = m.group(1)
password = m.group(2)

c = GoldikaClient(username, password)

with redirect_stdout(io.StringIO()):
    c.login()

paths = [
    "/api/v1/account",
    "/api/v1/account/balance",
    "/api/v1/account/balances",
    "/api/v1/wallet",
    "/api/v1/wallets",
    "/api/v1/wallet/balance",
    "/api/v1/user/wallet",
    "/api/auth/user/me",
]

for path in paths:
    try:
        r = c.session.get(
            c.BASE_URL + path,
            timeout=10
        )

        if r.status_code != 404:
            print()
            print("PATH:", path)
            print("STATUS:", r.status_code)
            print("RESPONSE:", r.text[:2000])

    except Exception as e:
        print()
        print("PATH:", path)
        print("ERROR:", repr(e))
