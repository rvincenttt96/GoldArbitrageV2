from datetime import datetime, timezone

from adapters.wallgold.client import WallGoldClient
from services.executor import Executor
from services.risk_manager import RiskManager
from core.models import Portfolio, Opportunity


API_KEY = "7969175|1JKem5nzDrdrYUfGMCITVFiwGa5eOqXd8zLC5PYE9425d863"


client = WallGoldClient(API_KEY)


opportunity = Opportunity(
    buy_platform="wallgold",
    sell_platform="wallgold",
    symbol="GLD_18C_750TMN",
    amount=0.007,
    buy_price=22000000,
    sell_price=22072000,
    gross_profit=5040,
    buy_fee=770,
    sell_fee=770,
    net_profit=100000,
    timestamp=datetime.now(timezone.utc)
)


portfolio = Portfolio(
    platform="wallgold",
    actual_cash=10000000,
    actual_gold=1,
    allowed_cash=10000000,
    allowed_gold=0.5,
    updated_at=datetime.now(timezone.utc)
)


executor = Executor(
    RiskManager()
)


result = executor.execute(
    opportunity,
    client,
    client,
    portfolio,
    portfolio
)


print(result)
