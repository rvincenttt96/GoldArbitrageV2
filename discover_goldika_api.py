import re
import requests
from urllib.parse import urljoin

BASE = "https://goldika.ir"

session = requests.Session()

session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/javascript,*/*"
})

print("FETCHING GOLDIKA FRONTEND...")

r = session.get(
    BASE,
    timeout=20
)

print("HOME STATUS:", r.status_code)

html = r.text

scripts = re.findall(
    r'<script[^>]+src=["\']([^"\']+)["\']',
    html,
    flags=re.I
)

print("SCRIPT FILES:", len(scripts))

keywords = (
    "balance",
    "wallet",
    "account",
    "profile",
    "inventory",
    "asset",
    "rial",
    "gold",
    "user",
    "credit",
)

found = set()

for src in scripts:

    url = urljoin(
        BASE,
        src
    )

    try:

        js = session.get(
            url,
            timeout=20
        )

        if js.status_code != 200:
            continue

        text = js.text

        paths = re.findall(
            r'["\']([^"\']*/api/[^"\']+)["\']',
            text
        )

        for path in paths:

            low = path.lower()

            if any(
                keyword in low
                for keyword in keywords
            ):
                found.add(path)

    except Exception as e:
        print(
            "SCRIPT ERROR:",
            url,
            repr(e)
        )


print()
print("===== POSSIBLE API ENDPOINTS =====")

for path in sorted(found):
    print(path)

print()
print("TOTAL:", len(found))
