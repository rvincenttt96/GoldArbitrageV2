from types import SimpleNamespace

from services.executor import Executor


class Risk:
    def check(self, *args):
        return True


class BuyExchange:

    def get_price(self, side):
        return SimpleNamespace(
            price=100000
        )

    def buy(self, amount):
        return {
            "success": True,
            "result": {
                "amount": amount
            }
        }


class SellExchange:

    def get_price(self, side):
        return SimpleNamespace(
            price=200000
        )

    def sell(self, amount):
        raise Exception(
            "SIMULATED SELL FAILURE"
        )


opportunity = SimpleNamespace(
    amount=1,
    buy_price=100000,
    sell_price=200000,
    buy_fee=0,
    sell_fee=0,
    net_profit=100000
)

executor = Executor(
    Risk()
)

result = executor.execute(
    opportunity,
    BuyExchange(),
    SellExchange(),
    None,
    None
)

print(result)
