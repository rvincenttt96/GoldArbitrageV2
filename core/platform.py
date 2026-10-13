"""Declarative description of a trading venue.

Every venue-specific number lives in a `PlatformSpec` loaded from
`config/platforms.toml`. Nothing in the strategy layer is allowed to branch on a
platform name; it reads the spec instead. Adding a venue is a config entry plus
an adapter class.

Amounts are integer milligrams throughout. Every venue in scope quotes 18k gold
in units that are whole milligrams (Milli trades in milli-grams, MelliGold's
floor is 10 mg, Goldika's sell payload is centigrams), so milligrams are the
natural atom and floats never enter the accounting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

MG_PER_GRAM = 1000


class Capability(StrEnum):
    """What a venue can actually do, as opposed to what we wish it did."""

    #: Publishes genuinely distinct bid and ask. Venues without this publish a
    #: single reference price and express their spread through the fee instead,
    #: so a naive bid/ask comparison across venues is not apples to apples.
    TWO_SIDED_QUOTE = "two_sided_quote"

    #: Quote carries a server-side identifier or expiry that makes it binding
    #: for a known window. Only these venues can take part in lock-then-verify
    #: execution.
    FIRM_QUOTE = "firm_quote"

    #: Order placement is split into a reservation call and a confirmation call,
    #: which lets us price the other leg before committing.
    INVOICE_FLOW = "invoice_flow"

    #: Order state can be read back after submission, so realised fills can be
    #: reconciled against the estimate.
    ORDER_STATUS = "order_status"


class FeeBasis(StrEnum):
    """What the proportional part of a fee is charged on."""

    #: Fee is a share of the cash value of the trade.
    CASH = "cash"

    #: Fee is a share of the gold weight, truncated to whole milligrams and then
    #: valued at the trade price. Milli works this way, and the truncation is
    #: worth modelling because it is what the venue actually bills.
    GOLD = "gold"


@dataclass(frozen=True)
class FeeSpec:
    """One side (buy or sell) of a venue's fee schedule.

    The three components compose, which is enough to express every schedule seen
    so far: a plain percentage (Goldika), a percentage with a minimum billable
    weight (WallGold's 0.4 g floor), a percentage billed in truncated gold
    (Milli), and a flat per-trade charge (Taline's 5,000 TMN).
    """

    rate: Decimal = Decimal(0)
    basis: FeeBasis = FeeBasis.CASH

    #: Trades lighter than this are billed as if they weighed this much. This is
    #: what turns a headline 0.5% into an effective 2% on a 0.1 g ticket.
    min_billable_mg: int = 0

    #: Flat charge applied per trade regardless of size.
    fixed_tmn: Decimal = Decimal(0)


@dataclass(frozen=True)
class LimitSpec:
    """Order-size constraints imposed by the venue."""

    min_order_mg: int = 1
    max_order_mg: int | None = None

    #: Order sizes must be whole multiples of this. Goldika's sell payload is
    #: denominated in centigrams, so its step is 10 mg.
    step_mg: int = 1

    def clamp(self, amount_mg: int) -> int:
        """Round `amount_mg` down onto the venue's tradable grid.

        Returns 0 when the amount cannot be expressed as a legal order.
        """
        if self.max_order_mg is not None:
            amount_mg = min(amount_mg, self.max_order_mg)
        amount_mg -= amount_mg % self.step_mg
        if amount_mg < self.min_order_mg:
            return 0
        return amount_mg


@dataclass(frozen=True)
class TreasurySpec:
    """When a venue's balances are too low to keep trading.

    Every trade drains cash from the venue we buy on and gold from the venue we
    sell on, and neither comes back on its own. Watching these levels is the
    difference between noticing a funding gap and discovering it as a missed
    opportunity.
    """

    #: Alert below these.
    min_cash_tmn: Decimal = Decimal(0)
    min_gold_mg: int = 0

    #: What a top-up should restore. Refilling only to the minimum guarantees
    #: another alert almost immediately.
    target_cash_tmn: Decimal = Decimal(0)
    target_gold_mg: int = 0

    #: Above this the venue is holding more than it needs and can fund others.
    surplus_cash_tmn: Decimal | None = None
    surplus_gold_mg: int | None = None


@dataclass(frozen=True)
class PlatformSpec:
    """Everything the strategy layer needs to know about one venue."""

    name: str
    display_name: str
    enabled: bool
    adapter: str
    buy_fee: FeeSpec
    sell_fee: FeeSpec
    limits: LimitSpec
    capabilities: frozenset[Capability] = field(default_factory=frozenset)

    #: How long a quote from this venue stays actionable. Used to reject stale
    #: prices before they are allowed to justify an order.
    quote_ttl_seconds: float = 30.0

    #: Set when the venue has been wired up but never verified against a real
    #: order. Such venues may be scanned but must not be traded.
    verified: bool = False

    treasury: TreasurySpec = field(default_factory=TreasurySpec)

    def can(self, capability: Capability) -> bool:
        return capability in self.capabilities

    @property
    def tradable(self) -> bool:
        """A venue is only tradable once it is both enabled and verified.

        Keeping these separate is deliberate: a newly added venue should be able
        to stream prices into the recorder while still being barred from placing
        orders.
        """
        return self.enabled and self.verified
