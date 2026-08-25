from datetime import datetime, timezone

from core.models import Quote
from services.fee_engine import FeeEngine
from services.arbitrage import ArbitrageEngine


buy_quote = Quote(
    platform="wallgold",
    symbol="GLD_18C_750TMN",
    side="buy",
    price=20800000,
    expires_at=datetime.now(timezone.utc),
    ttl=30,
    timestamp=datetime.now(timezone.utc)
)


sell_quote = Quote(
    platform="goldika",
    symbol="GLD_18C_750TMN",
    side="sell",
    price=21800000,
    expires_at=datetime.now(timezone.utc),
    ttl=30,
    timestamp=datetime.now(timezone.utc)
)


fee_engine = FeeEngine()

engine = ArbitrageEngine(
    fee_engine
)


opportunity = engine.evaluate(
    buy_quote,
    sell_quote,
    0.5
)


print(opportunity)
