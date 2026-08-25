from pathlib import Path
import re

p = Path("./live_bot.py")
s = p.read_text(encoding="utf-8")


if "trading_halted = False" not in s:

    s = re.sub(
        r'last_report_time\s*=\s*0',
        '''last_report_time = 0
last_trade_time = 0
trading_halted = False''',
        s,
        count=1
    )


s = re.sub(
    r'(?m)^        if opportunity:\s*$',
    '''        if (
            opportunity
            and not trading_halted
            and time.time() - last_trade_time >= 30
        ):''',
    s,
    count=1
)


old = '''            print(result)'''

new = '''            print(result)


            if result.get("status") == "completed":

                last_trade_time = time.time()


            elif result.get("status") in {
                "partial_execution",
                "execution_uncertain"
            }:

                trading_halted = True

                print(
                    "CRITICAL: EXECUTION UNCERTAIN/PARTIAL - TRADING HALTED"
                )'''


if old not in s:
    raise Exception(
        "print(result) target not found"
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

print("LIVE BOT SAFETY PATCH DONE")
