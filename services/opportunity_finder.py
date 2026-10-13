"""Pairwise scan for the best executable cross-venue trade.

Every venue pair is costed independently using that pair's own fee schedules and
size limits. No platform name appears anywhere in this module: adding a venue
does not change this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.fees import fee_breakpoints_mg, fee_tmn
from core.grading import DEFAULT_LADDER, Grade, GradeLadder
from core.models import Inventory, Opportunity, Quote, Rejection, utcnow
from core.platform import MG_PER_GRAM, PlatformSpec


@dataclass(frozen=True)
class StrategyLimits:
    """Thresholds a candidate must clear before it counts as an opportunity."""

    #: Absolute floor, in toman. Guards against trades too small to be worth the
    #: operational risk regardless of how good the percentage looks.
    min_net_profit_tmn: Decimal = Decimal(40_000)

    #: How much capital each quality band may commit. The ladder's own floor
    #: replaces a single proportional threshold: a weak signal trades small
    #: rather than not at all.
    grades: GradeLadder = DEFAULT_LADDER

    max_order_mg: int = 500

    #: Candidates whose quotes are older than the venue's TTL are dropped rather
    #: than traded. A stale quote is not a price, it is a memory of one.
    enforce_quote_freshness: bool = True


@dataclass
class GradedOpportunity:
    """An opportunity together with the band that decided its size."""

    opportunity: Opportunity
    grade: Grade

    def __str__(self) -> str:
        return f"[{self.grade.name}] {self.opportunity}"


@dataclass
class ScanResult:
    """The best opportunity found, plus a record of everything discarded."""

    best: GradedOpportunity | None
    rejections: list[Rejection]

    def reason_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.rejections:
            counts[r.reason] = counts.get(r.reason, 0) + 1
        return counts


class OpportunityFinder:
    def __init__(self, specs: dict[str, PlatformSpec], limits: StrategyLimits | None = None):
        self.specs = specs
        self.limits = limits or StrategyLimits()

    # -- costing -----------------------------------------------------------

    def build(
        self,
        buy_quote: Quote,
        sell_quote: Quote,
        amount_mg: int,
    ) -> Opportunity:
        buy_spec = self.specs[buy_quote.platform]
        sell_spec = self.specs[sell_quote.platform]

        return Opportunity(
            buy_platform=buy_quote.platform,
            sell_platform=sell_quote.platform,
            symbol=buy_quote.symbol,
            amount_mg=amount_mg,
            buy_price=buy_quote.price_tmn_per_gram,
            sell_price=sell_quote.price_tmn_per_gram,
            buy_fee=fee_tmn(buy_spec.buy_fee, amount_mg, buy_quote.price_tmn_per_gram),
            sell_fee=fee_tmn(sell_spec.sell_fee, amount_mg, sell_quote.price_tmn_per_gram),
            timestamp=utcnow(),
        )

    def net_buy_price(self, quote: Quote, amount_mg: int) -> Decimal:
        """All-in cost per gram of acquiring gold on this venue.

        This is the only price that may be compared across venues. Venues that
        publish a single reference price express their entire spread through the
        fee, so comparing raw quotes would rank them against venues that publish
        a real ask as though the spread did not exist.
        """
        spec = self.specs[quote.platform]
        fee = fee_tmn(spec.buy_fee, amount_mg, quote.price_tmn_per_gram)
        return quote.price_tmn_per_gram + fee * MG_PER_GRAM / amount_mg

    def net_sell_price(self, quote: Quote, amount_mg: int) -> Decimal:
        """All-in proceeds per gram of disposing of gold on this venue."""
        spec = self.specs[quote.platform]
        fee = fee_tmn(spec.sell_fee, amount_mg, quote.price_tmn_per_gram)
        return quote.price_tmn_per_gram - fee * MG_PER_GRAM / amount_mg

    # -- size search -------------------------------------------------------

    def candidate_sizes(
        self,
        buy_spec: PlatformSpec,
        sell_spec: PlatformSpec,
        ceiling_mg: int,
    ) -> list[int]:
        """Order sizes worth evaluating for this pair.

        Net profit is piecewise linear in size, kinking wherever a minimum
        billable weight kicks in. Only the ceiling and the kinks can be optimal,
        so evaluating those is exhaustive without scanning every milligram.
        """
        step = max(buy_spec.limits.step_mg, sell_spec.limits.step_mg)
        floor = max(buy_spec.limits.min_order_mg, sell_spec.limits.min_order_mg)

        def legal(mg: int) -> int:
            mg -= mg % step
            if mg < floor or mg > ceiling_mg:
                return 0
            if buy_spec.limits.clamp(mg) != mg or sell_spec.limits.clamp(mg) != mg:
                return 0
            return mg

        candidates = {legal(ceiling_mg)}
        for breakpoint in (
            *fee_breakpoints_mg(buy_spec.buy_fee),
            *fee_breakpoints_mg(sell_spec.sell_fee),
        ):
            # Both sides of a kink matter: just below it the fee is flat and the
            # trade may be too small, just above it the rate finally becomes the
            # headline one.
            candidates.add(legal(breakpoint))
            candidates.add(legal(breakpoint + step))
        candidates.add(legal(floor))

        return sorted(mg for mg in candidates if mg > 0)

    # -- scan --------------------------------------------------------------

    def find(
        self,
        quotes: list[Quote],
        inventories: dict[str, Inventory],
        tradable: set[str] | None = None,
    ) -> ScanResult:
        """Best opportunity across every ordered pair of venues."""
        rejections: list[Rejection] = []
        now = utcnow()

        buys: list[Quote] = []
        sells: list[Quote] = []
        for quote in quotes:
            spec = self.specs.get(quote.platform)
            if spec is None:
                continue
            if tradable is not None and quote.platform not in tradable:
                continue
            if self.limits.enforce_quote_freshness and not quote.is_fresh(
                spec.quote_ttl_seconds, now
            ):
                rejections.append(
                    Rejection(
                        quote.platform,
                        quote.platform,
                        0,
                        "stale_quote",
                        f"{quote.side} quote aged {quote.age_seconds(now):.1f}s",
                    )
                )
                continue
            (buys if quote.side == "buy" else sells).append(quote)

        best: GradedOpportunity | None = None

        for buy_quote in buys:
            for sell_quote in sells:
                if buy_quote.platform == sell_quote.platform:
                    continue

                candidate = self._best_for_pair(
                    buy_quote, sell_quote, inventories, rejections
                )
                if candidate is None:
                    continue
                if (
                    best is None
                    or candidate.opportunity.net_profit > best.opportunity.net_profit
                ):
                    best = candidate

        return ScanResult(best=best, rejections=rejections)

    def _best_for_pair(
        self,
        buy_quote: Quote,
        sell_quote: Quote,
        inventories: dict[str, Inventory],
        rejections: list[Rejection],
    ) -> GradedOpportunity | None:
        buy_spec = self.specs[buy_quote.platform]
        sell_spec = self.specs[sell_quote.platform]
        pair = (buy_quote.platform, sell_quote.platform)

        buy_inv = inventories.get(buy_quote.platform)
        sell_inv = inventories.get(sell_quote.platform)
        if buy_inv is None or sell_inv is None:
            rejections.append(Rejection(*pair, 0, "no_inventory_data"))
            return None

        affordable = self.limits.max_order_mg
        if buy_quote.price_tmn_per_gram > 0:
            affordable = int(
                buy_inv.available_cash * MG_PER_GRAM / buy_quote.price_tmn_per_gram
            )

        ceiling = min(self.limits.max_order_mg, sell_inv.available_gold_mg, affordable)

        if ceiling <= 0:
            rejections.append(Rejection(*pair, 0, "insufficient_inventory"))
            return None

        if ceiling < self.limits.max_order_mg:
            # Recorded even when a trade still goes ahead. "We saw the edge but
            # could only fund part of it" and "there was no edge" look identical
            # in a P&L series and call for completely different fixes: the first
            # is a rebalancing problem, the second is a market problem.
            binding = "cash" if affordable <= sell_inv.available_gold_mg else "gold"
            rejections.append(
                Rejection(
                    *pair,
                    ceiling,
                    "inventory_capped_size",
                    f"{binding} limited size to {ceiling}mg "
                    f"of {self.limits.max_order_mg}mg",
                )
            )

        sizes = self.candidate_sizes(buy_spec, sell_spec, ceiling)
        if not sizes:
            rejections.append(
                Rejection(*pair, ceiling, "below_min_order", f"ceiling {ceiling}mg")
            )
            return None

        # Grade the signal at the largest size the inventory allows, because
        # that is the honest measure of the opportunity. Sizing comes after.
        natural = max(
            (self.build(buy_quote, sell_quote, mg) for mg in sizes),
            key=lambda o: o.net_profit,
        )

        grade = self.limits.grades.classify(natural.return_fraction)
        if grade is None:
            rejections.append(
                Rejection(
                    *pair,
                    natural.amount_mg,
                    "below_lowest_grade",
                    f"{natural.return_fraction * 100:.3f}% vs "
                    f"{self.limits.grades.floor * 100:.2f}% needed",
                )
            )
            return None

        # The grade decides how much capital to commit, but never less than the
        # size at which this pair's minimum billable weights stop biting.
        # Trading below that costs more per gram, so a smaller position would be
        # a worse one, which is the opposite of what a lower grade should mean.
        floor_mg = self._efficient_floor(buy_spec, sell_spec)
        target = min(ceiling, max(floor_mg, int(ceiling * grade.capital_fraction)))
        eligible = [mg for mg in sizes if mg <= target] or [sizes[0]]
        opportunity = max(
            (self.build(buy_quote, sell_quote, mg) for mg in eligible),
            key=lambda o: o.net_profit,
        )

        problem = self._disqualify(opportunity, grade, buy_inv)
        if problem is not None:
            rejections.append(problem)
            return None

        return GradedOpportunity(opportunity, grade)

    def _disqualify(
        self,
        opportunity: Opportunity,
        grade: Grade,
        buy_inv: Inventory,
    ) -> Rejection | None:
        """Final checks on the sized trade, or None if it passes."""
        pair = (opportunity.buy_platform, opportunity.sell_platform)

        if opportunity.required_cash > buy_inv.available_cash:
            return Rejection(*pair, opportunity.amount_mg, "insufficient_cash")

        if opportunity.net_profit < self.limits.min_net_profit_tmn:
            return Rejection(
                *pair,
                opportunity.amount_mg,
                "below_min_profit",
                f"net {opportunity.net_profit:,.0f} at grade {grade.name}",
            )

        if opportunity.return_fraction < self.limits.grades.floor:
            # Sizing down to the grade's allowance pushed the trade under even
            # the lowest band. Better to skip than to take a position the ladder
            # would not have graded in the first place.
            return Rejection(
                *pair,
                opportunity.amount_mg,
                "grade_sizing_broke_the_edge",
                f"{opportunity.return_fraction * 100:.3f}% after sizing to "
                f"grade {grade.name}",
            )

        return None

    @staticmethod
    def _efficient_floor(buy_spec: PlatformSpec, sell_spec: PlatformSpec) -> int:
        """Smallest size at which neither venue's minimum billable weight bites.

        Below this, the fee is constant while the trade shrinks, so the
        effective rate climbs. WallGold's 0.4 g floor and MelliGold's 0.5 g floor
        both live here.
        """
        return max(
            buy_spec.buy_fee.min_billable_mg,
            sell_spec.sell_fee.min_billable_mg,
            buy_spec.limits.min_order_mg,
            sell_spec.limits.min_order_mg,
        )

    def _explain_miss(
        self,
        buy_quote: Quote,
        sell_quote: Quote,
        buy_spec: PlatformSpec,
        sell_spec: PlatformSpec,
        ceiling: int,
    ) -> Rejection:
        """Say how far short the route fell, not merely that it did.

        "no edge" and "edge, but 0.05% short" call for different responses, and
        only one of them means the market is the problem.
        """
        pair = (buy_quote.platform, sell_quote.platform)
        sizes = self.candidate_sizes(buy_spec, sell_spec, ceiling)
        if not sizes:
            return Rejection(*pair, ceiling, "below_min_order", f"ceiling {ceiling}mg")

        probe = self.build(buy_quote, sell_quote, sizes[-1])
        return Rejection(
            *pair,
            sizes[-1],
            "below_lowest_grade",
            f"{probe.return_fraction * 100:.3f}% vs "
            f"{self.limits.grades.floor * 100:.2f}% needed",
        )
