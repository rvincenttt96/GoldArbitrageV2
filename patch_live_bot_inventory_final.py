from pathlib import Path
import re


# =========================================================
# LIVE BOT
# =========================================================

p = Path("./live_bot.py")
s = p.read_text(encoding="utf-8-sig")


# ----- imports -----

if not re.search(
    r"(?m)^import json\s*$",
    s
):
    s = re.sub(
        r"(?m)^import time\s*$",
        "import time\nimport json",
        s,
        count=1
    )

if not re.search(
    r"(?m)^import sys\s*$",
    s
):
    s = re.sub(
        r"(?m)^import json\s*$",
        "import json\nimport sys",
        s,
        count=1
    )


# ----- safe Windows UTF-8 console -----

if "sys.stdout.reconfigure" not in s:

    marker = (
        "from datetime import datetime, timezone\n"
    )

    block = '''

# Safe UTF-8 output for Windows / Tee-Object.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="backslashreplace"
    )

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(
        encoding="utf-8",
        errors="backslashreplace"
    )

'''

    if marker not in s:
        raise Exception(
            "datetime import marker not found"
        )

    s = s.replace(
        marker,
        marker + block,
        1
    )


# ----- MAX_TRADE_AMOUNT -----

if not re.search(
    r"(?m)^from config\.settings import MAX_TRADE_AMOUNT\s*$",
    s
):

    marker = (
        "from services.risk_manager "
        "import RiskManager\n"
    )

    if marker not in s:
        raise Exception(
            "RiskManager import marker not found"
        )

    s = s.replace(
        marker,
        marker
        +
        "from config.settings import MAX_TRADE_AMOUNT\n",
        1
    )


# ----- create portfolios BEFORE scanner/finder -----

portfolio_pattern = re.compile(
    r'''(?m)^(?P<i>[ \t]+)goldika_portfolio\s*=\s*load_goldika_portfolio\(\)\s*
(?:[ \t]*\n)*
(?P=i)scan\s*=\s*scanner\.scan\(\)\s*$'''
)

m = portfolio_pattern.search(s)

if m:

    i = m.group("i")

    replacement = (
        f"{i}goldika_portfolio = load_goldika_portfolio()\n\n"
        f"{i}portfolios = {{\n"
        f'{i}    "wallgold": wallgold_portfolio,\n'
        f'{i}    "goldika": goldika_portfolio,\n'
        f'{i}    "miligold": miligold_portfolio\n'
        f"{i}}}\n\n"
        f"{i}scan = scanner.scan()"
    )

    s = portfolio_pattern.sub(
        replacement,
        s,
        count=1
    )

else:

    # If already patched, accept it.
    check = re.search(
        r'''(?s)goldika_portfolio\s*=\s*load_goldika_portfolio\(\).*?
portfolios\s*=\s*\{.*?
scan\s*=\s*scanner\.scan\(\)''',
        s
    )

    if not check:
        raise Exception(
            "Could not install portfolios block"
        )


# ----- inventory-aware finder call -----

finder_pattern = re.compile(
    r'''(?ms)^(?P<i>[ \t]+)opportunity\s*=\s*finder\.find\(
\s*scan\s*,
\s*(?:0\.5|MAX_TRADE_AMOUNT)\s*
(?:,\s*portfolios\s*)?
\)\s*$'''
)

m = finder_pattern.search(s)

if m:

    i = m.group("i")

    replacement = (
        f"{i}opportunity = finder.find(\n"
        f"{i}    scan,\n"
        f"{i}    MAX_TRADE_AMOUNT,\n"
        f"{i}    portfolios\n"
        f"{i})"
    )

    s = finder_pattern.sub(
        replacement,
        s,
        count=1
    )

else:

    if not re.search(
        r'''(?s)opportunity\s*=\s*finder\.find\(
\s*scan\s*,
\s*MAX_TRADE_AMOUNT\s*,
\s*portfolios\s*
\)''',
        s
    ):
        raise Exception(
            "finder.find call not found"
        )


# ----- Unicode-safe result logging -----

s, count = re.subn(
    r'(?m)^(?P<i>[ \t]*)print\(result\)\s*$',
    r'''\g<i>print(
\g<i>    json.dumps(
\g<i>        result,
\g<i>        ensure_ascii=True,
\g<i>        default=str
\g<i>    )
\g<i>)''',
    s,
    count=1
)

if count == 0 and "ensure_ascii=True" not in s:
    raise Exception(
        "result logging location not found"
    )


p.write_text(
    s,
    encoding="utf-8"
)


# =========================================================
# GOLDIKA LOGIN LOGGING
# =========================================================

p = Path("./adapters/goldika/client.py")
g = p.read_text(encoding="utf-8-sig")

pattern = re.compile(
    r'''(?m)^[ \t]*print\("LOGIN STATUS:",\s*r\.status_code\)\s*
[ \t]*data\s*=\s*r\.json\(\)\s*
[ \t]*print\("LOGIN RESPONSE:"\)\s*
[ \t]*print\(data\)\s*'''
)

m = pattern.search(g)

if m:

    indent = "        "

    replacement = (
        f'{indent}data = r.json()\n'
        f'{indent}print(\n'
        f'{indent}    "GOLDIKA LOGIN:",\n'
        f'{indent}    r.status_code,\n'
        f'{indent}    data.get("status", "unknown")\n'
        f'{indent})\n'
    )

    g = pattern.sub(
        replacement,
        g,
        count=1
    )


p.write_text(
    g,
    encoding="utf-8"
)


print("LIVE BOT INVENTORY PATCH: OK")
print("UNICODE SAFE LOGGING: OK")
print("GOLDIKA TOKEN LOGGING REMOVED: OK")
