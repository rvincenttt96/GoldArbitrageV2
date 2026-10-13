"""Watches balances and says what to move where.

Every trade drains cash from the venue we buy on and gold from the venue we sell
on, and since gold cannot be transferred between these venues, the balances
drift in one direction until the strategy simply stops finding fundable trades.

That drift is the real ceiling on this business, so it is worth alerting on
before it bites rather than discovering it as a signal we could not take.

Alerts are specific: which venue, how short, and where the money should come
from. A warning that says only "low balance" leaves the operator to work out the
useful part.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from core.models import Inventory
from core.platform import MG_PER_GRAM, PlatformSpec


class Asset(StrEnum):
    CASH = "cash"
    GOLD = "gold"


@dataclass(frozen=True)
class Shortfall:
    """A venue holding less than it needs to keep trading."""

    platform: str
    asset: Asset
    have: Decimal
    need: Decimal
    target: Decimal

    @property
    def missing(self) -> Decimal:
        return self.need - self.have

    @property
    def to_target(self) -> Decimal:
        """Amount that restores the target rather than merely the minimum.

        Topping up to the minimum guarantees another alert on the next trade.
        """
        return max(self.target, self.need) - self.have

    def describe(self) -> str:
        if self.asset is Asset.CASH:
            return (
                f"{self.platform}: cash {self.have:,.0f} TMN, "
                f"needs {self.need:,.0f}, short {self.missing:,.0f}"
            )
        return (
            f"{self.platform}: gold {self.have / MG_PER_GRAM:.3f}g, "
            f"needs {self.need / MG_PER_GRAM:.3f}g, "
            f"short {self.missing / MG_PER_GRAM:.3f}g"
        )


@dataclass(frozen=True)
class Transfer:
    """A concrete instruction: take this much from here, put it there."""

    asset: Asset
    source: str
    destination: str
    amount: Decimal

    def describe(self) -> str:
        if self.asset is Asset.CASH:
            return (
                f"withdraw {self.amount:,.0f} TMN from {self.source} "
                f"and deposit to {self.destination}"
            )
        return (
            f"move {self.amount / MG_PER_GRAM:.3f}g of gold from {self.source} "
            f"to {self.destination}"
        )


def find_shortfalls(
    specs: dict[str, PlatformSpec],
    inventories: dict[str, Inventory],
) -> list[Shortfall]:
    """Every venue-and-asset that has dropped below its configured minimum."""
    out: list[Shortfall] = []

    for name, spec in specs.items():
        inventory = inventories.get(name)
        if inventory is None or not spec.enabled:
            continue

        t = spec.treasury
        if t.min_cash_tmn and inventory.available_cash < t.min_cash_tmn:
            out.append(
                Shortfall(name, Asset.CASH, inventory.available_cash,
                          t.min_cash_tmn, t.target_cash_tmn)
            )
        if t.min_gold_mg and inventory.available_gold_mg < t.min_gold_mg:
            out.append(
                Shortfall(name, Asset.GOLD, Decimal(inventory.available_gold_mg),
                          Decimal(t.min_gold_mg), Decimal(t.target_gold_mg))
            )

    return out


def _surplus(spec: PlatformSpec, inventory: Inventory, asset: Asset) -> Decimal:
    """How much this venue could give up without dropping below its own target."""
    t = spec.treasury
    if asset is Asset.CASH:
        threshold = t.surplus_cash_tmn
        if threshold is None:
            threshold = max(t.target_cash_tmn, t.min_cash_tmn)
        return max(Decimal(0), inventory.available_cash - threshold)

    threshold = t.surplus_gold_mg
    if threshold is None:
        threshold = max(t.target_gold_mg, t.min_gold_mg)
    return max(Decimal(0), Decimal(inventory.available_gold_mg - threshold))


def plan_transfers(
    specs: dict[str, PlatformSpec],
    inventories: dict[str, Inventory],
    shortfalls: list[Shortfall] | None = None,
) -> list[Transfer]:
    """Match each shortfall against venues holding more than they need.

    Cash moves by bank transfer, which is slow but possible. Gold does not move
    between these venues at all, so a gold shortfall gets no transfer here: the
    only fixes are buying on the short venue or reducing how much we sell from
    it, and both are decisions rather than instructions.
    """
    shortfalls = shortfalls if shortfalls is not None else find_shortfalls(specs, inventories)
    transfers: list[Transfer] = []

    available = {
        name: _surplus(specs[name], inventory, Asset.CASH)
        for name, inventory in inventories.items()
        if name in specs
    }

    for shortfall in shortfalls:
        if shortfall.asset is not Asset.CASH:
            continue

        wanted = shortfall.to_target
        donors = sorted(
            ((n, amount) for n, amount in available.items()
             if n != shortfall.platform and amount > 0),
            key=lambda kv: -kv[1],
        )
        for donor, amount in donors:
            if wanted <= 0:
                break
            moved = min(amount, wanted)
            transfers.append(Transfer(Asset.CASH, donor, shortfall.platform, moved))
            available[donor] -= moved
            wanted -= moved

    return transfers


def format_alert(shortfalls: list[Shortfall], transfers: list[Transfer]) -> str:
    """Telegram message. Empty string when there is nothing to say."""
    if not shortfalls:
        return ""

    parts = ["<b>TREASURY ALERT</b>", ""]

    cash = [s for s in shortfalls if s.asset is Asset.CASH]
    gold = [s for s in shortfalls if s.asset is Asset.GOLD]

    if cash:
        parts.append("<b>Cash running low</b>")
        parts += [f"  <code>{s.describe()}</code>" for s in cash]
        parts.append("")

    if gold:
        parts.append("<b>Gold running low</b>")
        parts += [f"  <code>{s.describe()}</code>" for s in gold]
        parts.append("")

    if transfers:
        parts.append("<b>Suggested transfers</b>")
        parts += [f"  {i}. {t.describe()}" for i, t in enumerate(transfers, 1)]
        parts.append("")

    if gold and not any(t.asset is Asset.GOLD for t in transfers):
        # Say this explicitly rather than leaving a gold shortfall looking like
        # something a transfer will fix.
        parts.append(
            "<i>Gold cannot be transferred between these venues. A gold "
            "shortfall has to be bought on the venue that is short, or the "
            "route that drains it has to be paused.</i>"
        )

    return "\n".join(parts).strip()
