from pathlib import Path
import re
import io
import json
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

client = GoldikaClient(
    username,
    password
)

with redirect_stdout(io.StringIO()):
    data = client.login()


SECRET_WORDS = (
    "token",
    "password",
    "authorization",
    "secret",
    "jwt",
    "refresh",
)


def sanitize(obj):

    if isinstance(obj, dict):

        result = {}

        for key, value in obj.items():

            if any(
                word in str(key).lower()
                for word in SECRET_WORDS
            ):
                result[key] = "<REDACTED>"
            else:
                result[key] = sanitize(value)

        return result

    if isinstance(obj, list):
        return [
            sanitize(item)
            for item in obj
        ]

    return obj


safe = sanitize(data)

print("LOGIN RESPONSE KEYS:")
print(list(data.keys()))

print()
print("SANITIZED LOGIN RESPONSE:")
print(
    json.dumps(
        safe,
        ensure_ascii=False,
        indent=2
    )
)
