from pathlib import Path
import re


# =========================================================
# PATCH live_bot.py
# =========================================================

p = Path("./live_bot.py")
s = p.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------
# Imports
# ---------------------------------------------------------

if not re.search(r"(?m)^import json\s*$", s):
    s, n = re.subn(
        r"(?m)^import time\s*$",
        "import time\nimport json",
        s,
        count=1
    )
    if n != 1:
        raise Exception("Could not add import json")


if not re.search(r"(?m)^import sys\s*$", s):
    s, n = re.subn(
        r"(?m)^import json\s*$",
        "import json\nimport sys",
        s,
        count=1
    )
    if n != 1:
        raise Exception("Could not add import sys")


# ---------------------------------------------------------
# UTF-8 safe console
# ---------------------------------------------------------

if "sys.stdout.reconfigure" not in s:

    marker = "from datetime import datetime, timezone"

    if marker not in s:
        raise Exception("datetime import not found")

    block = '''

# Safe Unicode output on Windows / PowerShell / Tee-Object.
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

    s = s.replace(
        marker,
        marker + block,
        1
    )


# ---------------------------------------------------------
# MAX_TRADE_AMOUNT import
# ---------------------------------------------------------

if not re.search(
    r"(?m)^from config\.settings import MAX_TRADE_AMOUNT\s*$",
    s
):

    pattern = (
        r"(?m)^(from services\.risk_manager "
        r"import RiskManager\s*)$"
    )

    s, n = re.subn(
        pattern,
        r"\1\nfrom config.settings import MAX_TRADE_AMOUNT",
        s,
        count=1
    )

    if n != 1:
        raise Exception(
            "RiskManager import not found"
        )


# ---------------------------------------------------------
# Build portfolios BEFORE scanner/finder
# ---------------------------------------------------------

scan_match = re.search(
    r"(?m)^[ \t]*scan\s*=\s*scanner\.scan\(\)",
    s
)

if not scan_match:
    raise Exception("scanner.scan() not found")


before_scan = s[:scan_match.start()]

if "portfolios = {" not in before_scan:

    pattern = re.compile(
        r"(?m)^(?P<i>[ \t]*)"
        r"goldika_portfolio\s*=\s*"
        r"load_goldika_portfolio\(\)\s*$"
    )

    m = pattern.search(s)

    if not m:
        raise Exception(
            "goldika_portfolio line not found"
        )

    i = m.group("i")

    replacement = (
        f"{i}goldika_portfolio = load_goldika_portfolio()\n\n"
        f"{i}portfolios = {{\n"
        f'{i}    "wallgold": wallgold_portfolio,\n'
        f'{i}    "goldika": goldika_portfolio,\n'
        f'{i}    "miligold": miligold_portfolio\n'
        f"{i}}}"
    )

    s = (
        s[:m.start()]
        + replacement
        + s[m.end():]
    )


# ---------------------------------------------------------
# Replace old finder.find(scan, 0.5)
# ---------------------------------------------------------

old_finder = re.compile(
    r"(?ms)^"
    r"(?P<i>[ \t]*)"
    r"opportunity\s*=\s*finder\.find"
    r"\(\s*"
    r"scan\s*,\s*"
    r"0\.5\s*"
    r"\)"
)

m = old_finder.search(s)

if m:

    i = m.group("i")

    replacement = (
        f"{i}opportunity = finder.find(\n"
        f"{i}    scan,\n"
        f"{i}    MAX_TRADE_AMOUNT,\n"
        f"{i}    portfolios\n"
        f"{i})"
    )

    s = (
        s[:m.start()]
        + replacement
        + s[m.end():]
    )

else:

    already_new = re.search(
        r"(?s)opportunity\s*=\s*finder\.find"
        r"\(\s*scan\s*,\s*"
        r"MAX_TRADE_AMOUNT\s*,\s*"
        r"portfolios\s*\)",
        s
    )

    if not already_new:
        raise Exception(
            "finder.find call still not recognized"
        )


# ---------------------------------------------------------
# Replace unsafe print(result)
# AND halt BEFORE any logging/Telegram
# ---------------------------------------------------------

pattern = re.compile(
    r"(?m)^"
    r"(?P<i>[ \t]*)"
    r"print\(result\)\s*$"
)

m = pattern.search(s)

if m:

    i = m.group("i")

    replacement = (
        f'{i}result_status = result.get("status")\n\n'
        f"{i}# Emergency state is updated BEFORE logging.\n"
        f"{i}if result_status in {{\n"
        f'{i}    "partial_execution",\n'
        f'{i}    "execution_uncertain"\n'
        f"{i}}}:\n"
        f"{i}    trading_halted = True\n"
        f"{i}    print(\n"
        f'{i}        "CRITICAL: EXECUTION UNCERTAIN/PARTIAL "\n'
        f'{i}        "- TRADING HALTED"\n'
        f"{i}    )\n\n"
        f"{i}print(\n"
        f"{i}    json.dumps(\n"
        f"{i}        result,\n"
        f"{i}        ensure_ascii=True,\n"
        f"{i}        default=str\n"
        f"{i}    )\n"
        f"{i})"
    )

    s = (
        s[:m.start()]
        + replacement
        + s[m.end():]
    )

elif "result_status = result.get" not in s:
    raise Exception(
        "print(result) not found"
    )


# Existing status block may remain.
# Convert completed check to result_status when possible.
s = re.sub(
    r'if result\.get\("status"\) == "completed":',
    'if result_status == "completed":',
    s
)


p.write_text(
    s,
    encoding="utf-8"
)


# =========================================================
# PATCH Goldika login logging
# Never print bearer token again.
# =========================================================

p = Path("./adapters/goldika/client.py")
g = p.read_text(encoding="utf-8-sig")

old = re.compile(
    r'''(?m)^
(?P<i>[ \t]*)print\("LOGIN STATUS:",\s*r\.status_code\)\s*
(?P=i)data\s*=\s*r\.json\(\)\s*
(?P=i)print\("LOGIN RESPONSE:"\)\s*
(?P=i)print\(data\)\s*''',
    re.X
)

m = old.search(g)

if m:

    i = m.group("i")

    replacement = (
        f"{i}data = r.json()\n"
        f"{i}print(\n"
        f'{i}    "GOLDIKA LOGIN:",\n'
        f"{i}    r.status_code,\n"
        f'{i}    data.get("status", "unknown")\n'
        f"{i})\n"
    )

    g = (
        g[:m.start()]
        + replacement
        + g[m.end():]
    )


p.write_text(
    g,
    encoding="utf-8"
)


print("PATCH COMPLETE")
print("1. Inventory-aware finder connected")
print("2. Dynamic trade amount connected")
print("3. Emergency halt moved before logging")
print("4. Unicode-safe result logging enabled")
print("5. Goldika token logging removed")
