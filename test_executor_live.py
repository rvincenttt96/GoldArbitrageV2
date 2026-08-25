from datetime import datetime, timezone

from adapters.wallgold.client import WallGoldClient
from adapters.goldika.client import GoldikaClient

from services.executor import Executor
from services.risk_manager import RiskManager

from core.models import Portfolio, Opportunity


wallgold = WallGoldClient(
    "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"
)


goldika = GoldikaClient(
    "9362798093",
    "Rv6047484"
)


goldika.login()


opportunity = Opportunity(
    buy_platform="wallgold",
    sell_platform="goldika",
    symbol="GLD_18C_750TMN",
    amount=0.1,
    buy_price=22100000,
    sell_price=22200000,
    gross_profit=100000,
    buy_fee=0,
    sell_fee=0,
    net_profit=100000,
    timestamp=datetime.now(timezone.utc)
)


buy_portfolio = Portfolio(
    platform="wallgold",
    actual_cash=10000000,
    actual_gold=0,
    allowed_cash=10000000,
    allowed_gold=0.5,
    updated_at=datetime.now(timezone.utc)
)


sell_portfolio = Portfolio(
    platform="goldika",
    actual_cash=0,
    actual_gold=1,
    allowed_gold=0.5,
    allowed_cash=0,
    updated_at=datetime.now(timezone.utc)
)


executor = Executor(
    RiskManager()
)


result = executor.execute(
    opportunity,
    wallgold,
    goldika,
    buy_portfolio,
    sell_portfolio
)


print(result)
