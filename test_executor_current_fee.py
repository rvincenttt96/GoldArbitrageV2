from services.executor import Executor
from services.risk_manager import RiskManager
from core.models import Opportunity
from datetime import datetime


executor = Executor(
    RiskManager()
)

old = Opportunity(
    buy_platform="miligold",
    sell_platform="wallgold",
    symbol="GLD_18C_750TMN",
    amount=0.5,
    buy_price=21382000,
    sell_price=21874000,
    gross_profit=0,
    buy_fee=0,
    sell_fee=0,
    net_profit=0,
    timestamp=datetime.now()
)

current = executor._build_current_opportunity(
    old,
    21382000,
    21874000
)

print(current)

print(
    "EXPECTED MILLI BUY FEE =",
    2 / 1000 * 21382000
)

print(
    "EXPECTED WALLGOLD SELL FEE =",
    0.5 * 21874000 * 0.005
)

print("NO TRADE EXECUTED")
