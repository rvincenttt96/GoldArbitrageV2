from dataclasses import dataclass
from datetime import datetime


@dataclass
class PriceSnapshot:

    platform: str
    symbol: str
    buy: int
    sell: int
    timestamp: datetime


@dataclass
class Quote:

    platform: str
    symbol: str
    side: str
    price: int
    expires_at: datetime
    ttl: float
    timestamp: datetime


@dataclass
class Balance:

    platform: str
    currency: str
    amount: float
    locked_amount: float


@dataclass
class Order:

    platform: str
    order_id: str
    side: str
    amount: float
    price: int
    status: str
    timestamp: datetime


@dataclass
class Opportunity:

    buy_platform: str
    sell_platform: str

    symbol: str

    amount: float

    buy_price: int
    sell_price: int

    gross_profit: float

    buy_fee: float
    sell_fee: float

    net_profit: float

    timestamp: datetime
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Portfolio:

    platform: str

    cash_tmn: float

    gold_amount: float

    updated_at: datetime
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Portfolio:

    platform: str

    actual_cash: float
    actual_gold: float

    allowed_cash: float
    allowed_gold: float

    updated_at: datetime


    def available_cash(self):

        return min(
            self.actual_cash,
            self.allowed_cash
        )


    def available_gold(self):

        return min(
            self.actual_gold,
            self.allowed_gold
        )
