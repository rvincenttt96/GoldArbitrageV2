from decimal import ROUND_HALF_UP, Decimal

import pytest

from core.fees import effective_rate, fee_tmn
from core.platform import FeeBasis, FeeSpec

PRICE = Decimal(21_824_000)


def test_plain_percentage():
    spec = FeeSpec(rate=Decimal("0.005"))
    # 0.5 g at 21,824,000 -> 10,912,000 notional -> 0.5% = 54,560.
    # Matches the otcFee WallGold reported on the real fill in real_trade_once.log.
    assert fee_tmn(spec, 500, PRICE) == Decimal(54_560)


def test_min_billable_weight_dominates_small_tickets():
    spec = FeeSpec(rate=Decimal("0.005"), min_billable_mg=400)

    # Everything below the floor is billed as 0.4 g.
    assert fee_tmn(spec, 100, PRICE) == fee_tmn(spec, 400, PRICE)

    # Which quadruples the effective rate on a 0.1 g ticket.
    assert effective_rate(spec, 100, PRICE) == pytest.approx(Decimal("0.02"))
    assert effective_rate(spec, 400, PRICE) == pytest.approx(Decimal("0.005"))
    assert effective_rate(spec, 500, PRICE) == pytest.approx(Decimal("0.005"))


def test_gold_basis_truncates_to_whole_milligrams():
    spec = FeeSpec(rate=Decimal("0.005"), basis=FeeBasis.GOLD)

    # 333 mg * 0.5% = 1.665 mg, truncated to 1 mg of gold.
    assert fee_tmn(spec, 333, PRICE) == Decimal(1) * PRICE / 1000

    # 500 mg * 0.5% = 2.5 mg, truncated to 2 mg.
    assert fee_tmn(spec, 500, PRICE) == Decimal(2) * PRICE / 1000


def test_gold_basis_can_round_to_zero_on_tiny_tickets():
    spec = FeeSpec(rate=Decimal("0.005"), basis=FeeBasis.GOLD)
    # Below 200 mg the commission truncates away entirely. Worth asserting so it
    # is a known property rather than a surprise in a profit estimate.
    assert fee_tmn(spec, 199, PRICE) == Decimal(0)


def test_fixed_component_adds_on_top():
    spec = FeeSpec(rate=Decimal("0.005"), fixed_tmn=Decimal(5_000))
    assert fee_tmn(spec, 500, PRICE) == Decimal(59_560)


def test_zero_rate_is_free():
    assert fee_tmn(FeeSpec(), 500, PRICE) == Decimal(0)


def test_melligold_fees_match_a_real_round_trip():
    """Pinned to invoices 7075872 (buy) and 7076276 (sell), both 0.019 g.

    The published fee page claims a 2.5 سوت floor on both sides. The buy was
    charged 1 سوت and the sell 2 سوت, so the model follows the invoices. This is
    why a venue stays unverified until real orders have gone through it.
    """
    buy = FeeSpec(
        rate=Decimal("0.005"), basis=FeeBasis.GOLD,
        min_billable_mg=200, fixed_tmn=Decimal(38),
    )
    sell = FeeSpec(rate=Decimal("0.005"), basis=FeeBasis.GOLD, min_billable_mg=400)

    buy_price = Decimal(22_077_668)
    sell_price = Decimal(22_037_588)

    # fee_price 22,078 is one milligram; maintenance_cost adds 38.
    assert fee_tmn(buy, 19, buy_price).quantize(Decimal("1")) == Decimal(22_116)
    # fee_price 44,075 is two milligrams, and sells carry no maintenance charge.
    assert fee_tmn(sell, 19, sell_price).quantize(Decimal("1")) == Decimal(44_075)

    # The venue rounds each line to the toman before summing, so the model lands
    # within a toman. One pair of invoices cannot pin down the rounding rule and
    # guessing it would be over-fitting.
    assert abs(Decimal(19) * buy_price / 1000 + fee_tmn(buy, 19, buy_price)
               - Decimal(441_592)) <= 1
    assert abs(Decimal(19) * sell_price / 1000 - fee_tmn(sell, 19, sell_price)
               - Decimal(374_639)) <= 1


def test_melligold_round_trip_is_ruinous_small_and_ordinary_large():
    """The floors are what punish small tickets, not the rate.

    The measured 19 mg round trip cost 66,953 on 419,476 of notional. The same
    trip at half a gram costs about 1%, which is where MelliGold becomes usable.
    """
    buy = FeeSpec(rate=Decimal("0.005"), basis=FeeBasis.GOLD, min_billable_mg=200)
    sell = FeeSpec(rate=Decimal("0.005"), basis=FeeBasis.GOLD, min_billable_mg=400)
    price = Decimal(22_050_000)

    def round_trip(mg):
        notional = Decimal(mg) * price / 1000
        return (fee_tmn(buy, mg, price) + fee_tmn(sell, mg, price)) / notional

    assert round_trip(19) > Decimal("0.15")
    assert round_trip(500) == pytest.approx(Decimal("0.009"), abs=Decimal("0.002"))


def test_wallgold_fee_matches_the_real_fill():
    """Reconciled against order 6055730: 0.5 g at 22,082,000 cost 55,205."""
    spec = FeeSpec(rate=Decimal("0.005"), min_billable_mg=400)
    assert fee_tmn(spec, 500, Decimal(22_082_000)) == Decimal(55_205)


def test_miligold_commission_matches_the_venue():
    """Pinned to /api/v1/trade/commission, read live on 2026-09-01.

    The commission is billed in whole milligrams of gold with a floor of one, so
    the effective rate is 1.0% at 100 mg, 0.4% at 500 mg and 0.5% at a gram. The
    dip at 500 mg is truncation working in our favour and is real money, so the
    model reproduces it rather than rounding it away.
    """
    spec = FeeSpec(rate=Decimal("0.005"), basis=FeeBasis.GOLD, min_billable_mg=200)
    price = Decimal(21_553_000)

    def commission_mg(amount_mg: int) -> Decimal:
        return fee_tmn(spec, amount_mg, price) / price * 1000

    assert commission_mg(100) == 1
    assert commission_mg(200) == 1
    assert commission_mg(500) == 2
    assert commission_mg(1000) == 5
    assert commission_mg(2000) == 10

    assert effective_rate(spec, 500, price) == pytest.approx(Decimal("0.004"))


def test_wallgold_floor_applies_to_sells_only():
    """Pinned to real order history read on 2026-09-01.

    Three 0.1 g buys were each charged exactly 0.5%, while a 0.1 g sell was
    billed as 0.4 g and a 0.007 g sell was billed as 0.4 g too, costing 28.57%
    of notional. So the floor is a property of the sell side, and treating it as
    a general minimum trade size would rule out perfectly good buy legs.
    """
    buy = FeeSpec(rate=Decimal("0.005"))
    sell = FeeSpec(rate=Decimal("0.005"), min_billable_mg=400)

    def charged(spec, mg, price):
        # The venue rounds the fee to the toman; the model keeps the fraction.
        return fee_tmn(spec, mg, Decimal(price)).quantize(Decimal("1"), ROUND_HALF_UP)

    # Buys, from orders at 21,910,000 / 22,042,000 / 22,107,000.
    assert charged(buy, 100, 21_910_000) == Decimal(10_955)
    assert charged(buy, 100, 22_042_000) == Decimal(11_021)
    assert charged(buy, 100, 22_107_000) == Decimal(11_054)

    # Sells below the floor, from orders at 21,719,000 and 22,072,000.
    assert charged(sell, 100, 21_719_000) == Decimal(43_438)
    assert charged(sell, 7, 22_072_000) == Decimal(44_144)
    assert effective_rate(sell, 7, Decimal(22_072_000)) > Decimal("0.28")

    # Sells above it are charged the headline rate: 0.453 g and 0.5 g.
    assert charged(sell, 453, 22_058_000) == Decimal(49_961)
    assert effective_rate(sell, 500, Decimal(22_082_000)) == Decimal("0.005")
