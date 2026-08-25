from datetime import datetime, timezone

from core.models import Portfolio, Opportunity
from services.risk_manager import RiskManager


opportunity = Opportunity(
    buy_platform="wallgold",
    sell_platform="goldika",
    symbol="GLD_18C_750TMN",
    amount=0.5,
    buy_price=20800000,
    sell_price=21800000,
    gross_profit=500000,
    buy_fee=52000,
    sell_fee=130800,
    net_profit=307200,
    timestamp=datetime.now(timezone.utc)
)


wallgold_portfolio = Portfolio(
    platform="wallgold",
    cash_tmn=10000000,
    gold_amount=0.5,
    updated_at=datetime.now(timezone.utc)
)


goldika_portfolio = Portfolio(
    platform="goldika",
    cash_tmn=10000000,
    gold_amount=0.5,
    updated_at=datetime.now(timezone.utc)
)


risk = RiskManager()


result = risk.check(
    opportunity,
    wallgold_portfolio,
    goldika_portfolio
)


print("RISK CHECK:")
print(result)
