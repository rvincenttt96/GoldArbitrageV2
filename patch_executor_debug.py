from pathlib import Path

p = Path("./services/executor.py")

s = p.read_text(encoding="utf-8")

s = s.replace(
'''        buy_order = buy_exchange.buy(
            opportunity.amount
        )


        sell_order = sell_exchange.sell(
            opportunity.amount
        )''',
'''        try:
            buy_order = buy_exchange.buy(
                opportunity.amount
            )
        except Exception as e:
            print("BUY ERROR:", repr(e))
            raise


        try:
            sell_order = sell_exchange.sell(
                opportunity.amount
            )
        except Exception as e:
            print("SELL ERROR:", repr(e))
            raise'''
)

p.write_text(s, encoding="utf-8")

print("DONE")
