"""Fee arithmetic driven entirely by `FeeSpec`.

This replaces the per-platform `if platform == ...` chains. Every venue's
schedule is data, so a new venue costs a config entry rather than an edit to the
profit calculation.
"""

from __future__ import annotations

from decimal import Decimal

from core.platform import MG_PER_GRAM, FeeBasis, FeeSpec


def fee_tmn(spec: FeeSpec, amount_mg: int, price_tmn_per_gram: Decimal) -> Decimal:
    """Cost in toman of trading `amount_mg` at `price_tmn_per_gram`."""
    billable_mg = max(amount_mg, spec.min_billable_mg)

    if spec.basis is FeeBasis.GOLD:
        # Billed as a weight of gold truncated to whole milligrams, then valued
        # at the trade price. Truncation favours the trader by up to one
        # milligram and is what the venue actually charges, so modelling it
        # keeps the estimate from drifting against the invoice.
        commission_mg = int(Decimal(billable_mg) * spec.rate)
        proportional = Decimal(commission_mg) * price_tmn_per_gram / MG_PER_GRAM
    else:
        value_tmn = Decimal(billable_mg) * price_tmn_per_gram / MG_PER_GRAM
        proportional = value_tmn * spec.rate

    return proportional + spec.fixed_tmn


def effective_rate(spec: FeeSpec, amount_mg: int, price_tmn_per_gram: Decimal) -> Decimal:
    """Fee as a fraction of notional.

    Diverges from `spec.rate` wherever a minimum billable weight or a flat
    charge dominates, which is exactly the region where small tickets quietly
    stop being worth trading.
    """
    notional = Decimal(amount_mg) * price_tmn_per_gram / MG_PER_GRAM
    if notional <= 0:
        return Decimal(0)
    return fee_tmn(spec, amount_mg, price_tmn_per_gram) / notional


def fee_breakpoints_mg(spec: FeeSpec) -> list[int]:
    """Sizes at which this schedule's marginal cost changes.

    A minimum billable weight makes net profit non-monotonic in size: below the
    floor the fee is constant, above it the fee grows. Any search for the best
    order size has to evaluate the floor itself rather than assume that bigger is
    always better.
    """
    return [spec.min_billable_mg] if spec.min_billable_mg > 0 else []
