"""Value objects shared by the scanner, the strategy and the executor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from core.platform import MG_PER_GRAM


def utcnow() -> datetime:
    """Timezone-aware now.

    Everything in this codebase is aware and in UTC. Mixing aware and naive
    datetimes raises the moment two of them are compared, and quote freshness
    checks compare them constantly.
    """
    return datetime.now(UTC)


@dataclass(frozen=True)
class Quote:
    """A price from one venue for one side of the market."""

    platform: str
    symbol: str
    side: str
    price_tmn_per_gram: Decimal
    timestamp: datetime

    #: Venue-side handle for this price, where one exists. Goldika requires it
    #: on the order payload; venues without it use None.
    price_id: str | None = None

    #: When the venue itself says the price stops being binding. None means the
    #: venue makes no such promise and `PlatformSpec.quote_ttl_seconds` applies.
    expires_at: datetime | None = None

    def age_seconds(self, now: datetime | None = None) -> float:
        return ((now or utcnow()) - self.timestamp).total_seconds()

    def is_fresh(self, ttl_seconds: float, now: datetime | None = None) -> bool:
        """Whether this quote may still justify an order.

        Honours the venue's own expiry when it publishes one and falls back to
        the configured TTL otherwise.
        """
        now = now or utcnow()
        if self.expires_at is not None and now >= self.expires_at:
            return False
        return self.age_seconds(now) <= ttl_seconds


@dataclass(frozen=True)
class Opportunity:
    """A costed two-legged trade: buy on one venue, sell on another."""

    buy_platform: str
    sell_platform: str
    symbol: str
    amount_mg: int
    buy_price: Decimal
    sell_price: Decimal
    buy_fee: Decimal
    sell_fee: Decimal
    timestamp: datetime

    @property
    def amount_grams(self) -> Decimal:
        return Decimal(self.amount_mg) / MG_PER_GRAM

    @property
    def buy_value(self) -> Decimal:
        return self.buy_price * self.amount_grams

    @property
    def sell_value(self) -> Decimal:
        return self.sell_price * self.amount_grams

    @property
    def gross_profit(self) -> Decimal:
        return self.sell_value - self.buy_value

    @property
    def net_profit(self) -> Decimal:
        return self.gross_profit - self.buy_fee - self.sell_fee

    @property
    def required_cash(self) -> Decimal:
        return self.buy_value + self.buy_fee

    @property
    def return_fraction(self) -> Decimal:
        """Net profit per toman deployed.

        The threshold that matters. An absolute profit floor means something
        completely different at 0.1 g than at 0.5 g.
        """
        if self.buy_value <= 0:
            return Decimal(0)
        return self.net_profit / self.buy_value

    def __str__(self) -> str:
        return (
            f"{self.buy_platform}->{self.sell_platform} "
            f"{self.amount_mg}mg net={self.net_profit:,.0f} "
            f"({self.return_fraction * 100:.3f}%)"
        )


@dataclass(frozen=True)
class Inventory:
    """What one venue is holding for us right now."""

    platform: str
    cash_tmn: Decimal
    gold_mg: int
    updated_at: datetime

    #: Optional per-venue ceilings, so exposure to any single venue can be
    #: capped independently of what is actually sitting there.
    max_cash_tmn: Decimal | None = None
    max_gold_mg: int | None = None

    @property
    def available_cash(self) -> Decimal:
        if self.max_cash_tmn is None:
            return self.cash_tmn
        return min(self.cash_tmn, self.max_cash_tmn)

    @property
    def available_gold_mg(self) -> int:
        if self.max_gold_mg is None:
            return self.gold_mg
        return min(self.gold_mg, self.max_gold_mg)


@dataclass(frozen=True)
class Rejection:
    """Why a candidate trade was not taken.

    Recorded for every rejected candidate. The distribution of reasons is the
    fastest way to tell "the edge never appears" apart from "the edge appears and
    we keep failing to act on it", and those two call for opposite fixes.
    """

    buy_platform: str
    sell_platform: str
    amount_mg: int
    reason: str
    detail: str = ""
