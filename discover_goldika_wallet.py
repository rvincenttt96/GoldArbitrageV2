import re
import requests
from urllib.parse import urljoin, urlparse

BASE = "https://goldika.ir"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*"
})

seen = set()
queue = []
matches = set()

KEYWORDS = re.compile(
    r"wallet|balance|inventory|asset|credit|rial|cash|account",
    re.I
)

def add_js(url):
    url = urljoin(BASE, url)

    if urlparse(url).netloc != urlparse(BASE).netloc:
        return

    if ".js" not in url:
        return

    if url not in seen and url not in queue:
        queue.append(url)


print("FETCHING HOME...")

home = session.get(
    BASE,
    timeout=20
)

print("HOME:", home.status_code)

for src in re.findall(
    r'''(?:src|href)=["']([^"']+\.js[^"']*)["']''',
    home.text,
    flags=re.I
):
    add_js(src)


processed = 0

while queue and processed < 200:

    url = queue.pop(0)

    if url in seen:
        continue

    seen.add(url)
    processed += 1

    try:
        r = session.get(
            url,
            timeout=15
        )

        if r.status_code != 200:
            continue

        text = r.text

        print(
            f"SCAN {processed}:",
            url.split("/")[-1],
            len(text)
        )

        # Find dynamically referenced JS chunks
        for item in re.findall(
            r'''["']([^"']+\.js(?:\?[^"']*)?)["']''',
            text
        ):
            add_js(item)

        # Search interesting keyword contexts
        for m in KEYWORDS.finditer(text):

            start = max(
                0,
                m.start() - 250
            )

            end = min(
                len(text),
                m.end() + 350
            )

            context = text[start:end]

            context = re.sub(
                r"\s+",
                " ",
                context
            )

            # Keep contexts likely related to backend/API
            low = context.lower()

            if (
                "/api" in low
                or
                "api." in low
                or
                "axios" in low
                or
                "fetch(" in low
                or
                "baseurl" in low
            ):
                matches.add(context)

    except Exception as e:
        print(
            "ERROR:",
            url,
            repr(e)
        )


print()
print("======================================")
print("POSSIBLE GOLDIKA WALLET/BALANCE CODE")
print("======================================")

for i, item in enumerate(
    sorted(matches),
    1
):
    print()
    print(f"--- MATCH {i} ---")
    print(item[:1200])


print()
print("JS FILES SCANNED:", len(seen))
print("MATCHES:", len(matches))
