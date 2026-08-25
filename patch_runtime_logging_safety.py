from pathlib import Path

# =========================================================
# PATCH live_bot.py
# =========================================================

p = Path("./live_bot.py")
s = p.read_text(encoding="utf-8-sig")

if "import json" not in s:
    s = s.replace(
        "import time\n",
        "import time\nimport json\nimport sys\n",
        1
    )

encoding_block = '''# Force safe UTF-8 logging on Windows/piped PowerShell output.
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

marker = "from datetime import datetime, timezone\n\n"

if encoding_block not in s:

    if marker not in s:
        raise Exception(
            "live_bot import marker not found"
        )

    s = s.replace(
        marker,
        marker + encoding_block,
        1
    )


old = '''            result = executor.execute(
                opportunity,
                buy_exchange,
                sell_exchange,
                buy_portfolio,
                sell_portfolio
            )
            print(result)

            try:
                send_trade_result(opportunity, result)
            except Exception as e:
                print("TELEGRAM TRADE ERROR:", repr(e))

            if result.get("status") == "completed":
                last_trade_time = time.time()
            elif result.get("status") in {
                "partial_execution",
                "execution_uncertain"
            }:
                trading_halted = True
                print("CRITICAL: EXECUTION UNCERTAIN/PARTIAL - TRADING HALTED")
'''

new = '''            result = executor.execute(
                opportunity,
                buy_exchange,
                sell_exchange,
                buy_portfolio,
                sell_portfolio
            )

            # Safety state must be updated BEFORE logging/Telegram.
            # Logging must never be able to bypass emergency halt.
            result_status = result.get("status")

            if result_status == "completed":
                last_trade_time = time.time()

            elif result_status in {
                "partial_execution",
                "execution_uncertain"
            }:
                trading_halted = True

                print(
                    "CRITICAL: EXECUTION UNCERTAIN/PARTIAL "
                    "- TRADING HALTED"
                )

            # ASCII-safe serialization prevents Windows charmap
            # failures when an exchange returns Persian messages.
            print(
                json.dumps(
                    result,
                    ensure_ascii=True,
                    default=str
                )
            )

            try:
                send_trade_result(opportunity, result)
            except Exception as e:
                print(
                    "TELEGRAM TRADE ERROR:",
                    repr(e)
                )
'''

if old not in s:
    raise Exception(
        "live_bot execution-result block not found"
    )

s = s.replace(
    old,
    new,
    1
)

p.write_text(
    s,
    encoding="utf-8"
)


# =========================================================
# PATCH Goldika login logging
# =========================================================

p = Path("./adapters/goldika/client.py")
s = p.read_text(encoding="utf-8-sig")

old = '''        print("LOGIN STATUS:", r.status_code)
        data = r.json()
        print("LOGIN RESPONSE:")
        print(data)
'''

new = '''        data = r.json()

        print(
            "GOLDIKA LOGIN:",
            r.status_code,
            data.get("status", "unknown")
        )
'''

if old not in s:
    raise Exception(
        "Goldika login logging block not found"
    )

s = s.replace(
    old,
    new,
    1
)

p.write_text(
    s,
    encoding="utf-8"
)

print("UNICODE + HALT SAFETY PATCH APPLIED")
print("GOLDIKA TOKEN LOGGING REMOVED")
