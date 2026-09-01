"""The contract every venue adapter has to satisfy.

An adapter's job is to hide one venue's API behind this interface and to decide,
for itself, whether its own responses mean success. It must never hand a raw
response dict up to the executor: a shared response parser cannot tell a Goldika
error apart from a Milli one and will eventually guess wrong on a live order.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable

from core.models import Quote


class AdapterError(RuntimeError):
    """The venue said no, and we know it did not trade."""


class UncertainExecutionError(RuntimeError):
    """We do not know whether an order was placed.

    Raised for network failures on order submission, where the request may have
    reached the venue. Callers must halt and reconcile by hand rather than retry;
    a retry here is how one order becomes two.
    """


@dataclass(frozen=True)
class OrderResult:
    """A confirmed fill, as reported by the venue."""

    platform: str
    order_id: str
    side: str
    amount_mg: int

    #: Price the venue says it actually filled at, when it says. Left as None by
    #: venues that do not report it, which is itself worth knowing: those legs
    #: can only ever be reconciled from balance deltas.
    filled_price: Decimal | None = None
    fee_tmn: Decimal | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Reservation:
    """A price held by the venue, pending confirmation.

    Only venues with the `invoice_flow` capability can produce one. It is what
    makes lock-then-verify execution possible: the price is binding for
    `valid_for_seconds`, so the other leg can be checked before committing.
    """

    platform: str
    reservation_id: str
    side: str
    amount_mg: int
    price_tmn_per_gram: Decimal
    fee_tmn: Decimal
    valid_for_seconds: float
    raw: dict = field(default_factory=dict)


@runtime_checkable
class SupportsReservation(Protocol):
    """Implemented by adapters whose venue splits reserve from confirm."""

    def reserve(self, side: str, amount_mg: int) -> Reservation: ...

    def confirm(self, reservation: Reservation) -> OrderResult: ...


class GoldAdapter(ABC):
    """Minimum surface required of every venue."""

    #: Must match the key in platforms.toml.
    name: str

    @abstractmethod
    def login(self) -> None:
        """Authenticate. Safe to call again to refresh an expired session."""

    @abstractmethod
    def get_quote(self, side: str) -> Quote:
        """Current price for `side`, which is 'buy' or 'sell'.

        Venues that publish only one reference price return it for both sides and
        must not declare the `two_sided_quote` capability, so the strategy layer
        knows their spread lives in the fee instead.
        """

    @abstractmethod
    def get_inventory(self) -> tuple[Decimal, int]:
        """Spendable cash in toman and spendable gold in milligrams."""

    @abstractmethod
    def buy(self, amount_mg: int) -> OrderResult:
        """Buy gold. Raises `AdapterError` on refusal.

        Raises `UncertainExecutionError` when the outcome is unknown. Never
        retries internally.
        """

    @abstractmethod
    def sell(self, amount_mg: int) -> OrderResult:
        """Sell gold. Same contract as `buy`."""

    def get_order(self, order_id: str) -> OrderResult:
        """Read an order back for reconciliation.

        Optional; only venues declaring `order_status` need to implement it.
        """
        raise NotImplementedError(f"{self.name} cannot read orders back")
