from pathlib import Path

p = Path("./live_bot.py")
s = p.read_text(encoding="utf-8")


old_import = (
    "from services.telegram "
    "import send_market_report"
)

new_import = '''from services.telegram import (
    send_market_report,
    send_trade_signal,
    send_trade_result,
)'''

if old_import in s:

    s = s.replace(
        old_import,
        new_import,
        1
    )


old_report = '''        if time.time() - last_report_time >= 1800:

            send_market_report(scan)

            last_report_time = time.time()'''


new_report = '''        if time.time() - last_report_time >= 1800:

            last_report_time = time.time()

            try:

                send_market_report(scan)

            except Exception as e:

                print(
                    "TELEGRAM REPORT ERROR:",
                    repr(e)
                )'''


if old_report not in s:
    raise Exception(
        "market report block not found"
    )

s = s.replace(
    old_report,
    new_report,
    1
)


old_execute = '''            print("EXECUTING REAL TRADE")'''


new_execute = '''            last_trade_time = time.time()

            print("EXECUTING REAL TRADE")

            try:

                send_trade_signal(
                    opportunity
                )

            except Exception as e:

                print(
                    "TELEGRAM SIGNAL ERROR:",
                    repr(e)
                )'''


if old_execute not in s:
    raise Exception(
        "execution block not found"
    )

s = s.replace(
    old_execute,
    new_execute,
    1
)


old_result = '''            print(result)


            if result.get("status") == "completed":'''


new_result = '''            print(result)


            try:

                send_trade_result(
                    opportunity,
                    result
                )

            except Exception as e:

                print(
                    "TELEGRAM TRADE ERROR:",
                    repr(e)
                )


            if result.get("status") == "completed":'''


if old_result not in s:
    raise Exception(
        "result block not found"
    )

s = s.replace(
    old_result,
    new_result,
    1
)


p.write_text(
    s,
    encoding="utf-8"
)

print(
    "LIVE BOT TELEGRAM PATCH DONE"
)
