from datetime import datetime, timezone

from core.models import Opportunity, Portfolio, Quote
from services.executor import Executor
from services.risk_manager import RiskManager


def portfolio(name, cash, gold):
    return Portfolio(
        platform=name,
        actual_cash=cash,
        actual_gold=gold,
        allowed_cash=cash,
        allowed_gold=gold,
        updated_at=datetime.now(timezone.utc)
    )


def opportunity():
    return Opportunity(
        buy_platform="miligold",
        sell_platform="wallgold",
        symbol="GLD_18C_750TMN",
        amount=0.5,
        buy_price=21382000,
        sell_price=21874000,
        gross_profit=246000,
        buy_fee=42764,
        sell_fee=54685,
        net_profit=148551,
        timestamp=datetime.now()
    )


class FakeBuyExchange:

    def get_price(self, side):
        return Quote(
            platform="miligold",
            symbol="GLD_18C_750TMN",
            side=side,
            price=21382000,
            price_id=0,
            expires_at=datetime.now(),
            ttl=30,
            timestamp=datetime.now()
        )

    def buy(self, amount):
        return {
            "code": 0,
            "data": {
                "invoiceStatus": "DONE"
            }
        }


class FakeSellExchange:

    def get_price(self, side):
        return Quote(
            platform="wallgold",
            symbol="GLD_18C_750TMN",
            side=side,
            price=21874000,
            price_id=0,
            expires_at=datetime.now(),
            ttl=30,
            timestamp=datetime.now()
        )

    def sell(self, amount):
        return {
            "success": True,
            "result": {
                "amount": str(amount)
            }
        }


class FakeBadPriceSellExchange:

    def get_price(self, side):
        return Quote(
            platform="wallgold",
            symbol="GLD_18C_750TMN",
            side=side,
            price=21400000,
            price_id=0,
            expires_at=datetime.now(),
            ttl=30,
            timestamp=datetime.now()
        )

    def sell(self, amount):
        raise Exception(
            "SELL MUST NOT BE CALLED"
        )


class FakeFailingSellExchange:

    def get_price(self, side):
        return Quote(
            platform="wallgold",
            symbol="GLD_18C_750TMN",
            side=side,
            price=21874000,
            price_id=0,
            expires_at=datetime.now(),
            ttl=30,
            timestamp=datetime.now()
        )

    def sell(self, amount):
        raise Exception(
            "SIMULATED SELL FAILURE"
        )


executor = Executor(
    RiskManager()
)

buy_portfolio = portfolio(
    "miligold",
    11263249,
    0.504
)

sell_portfolio = portfolio(
    "wallgold",
    18664387,
    5.199
)


print("===================================")
print("TEST 1 - SUCCESS")
print("===================================")

r1 = executor.execute(
    opportunity(),
    FakeBuyExchange(),
    FakeSellExchange(),
    buy_portfolio,
    sell_portfolio
)

print(r1)

assert r1["status"] == "completed"
assert r1["current_buy_fee"] == 42764.0
assert r1["current_sell_fee"] == 54685.0


print()
print("===================================")
print("TEST 2 - PRICE MOVED")
print("===================================")

r2 = executor.execute(
    opportunity(),
    FakeBuyExchange(),
    FakeBadPriceSellExchange(),
    buy_portfolio,
    sell_portfolio
)

print(r2)

assert r2["status"] == "rejected"
assert r2["reason"] == "price_moved"


print()
print("===================================")
print("TEST 3 - SELL FAILURE")
print("===================================")

r3 = executor.execute(
    opportunity(),
    FakeBuyExchange(),
    FakeFailingSellExchange(),
    buy_portfolio,
    sell_portfolio
)

print(r3)

assert r3["status"] == "partial_execution"
assert r3["stage"] == "sell"
assert r3["halt_required"] is True


print()
print("===================================")
print("ALL EXECUTOR SAFETY TESTS PASSED")
print("NO REAL TRADE EXECUTED")
print("===================================")
