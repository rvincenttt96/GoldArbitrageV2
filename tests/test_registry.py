from decimal import Decimal
from pathlib import Path

import pytest

from config.loader import ConfigError, load_platforms
from core.platform import Capability, FeeBasis

CONFIG = Path(__file__).resolve().parents[1] / "config" / "platforms.toml"


def test_shipped_config_loads():
    specs = load_platforms(CONFIG)
    assert {"wallgold", "goldika", "miligold", "melligold", "talasea"} <= set(specs)


def test_wallgold_sell_floor_is_configured_not_hardcoded():
    spec = load_platforms(CONFIG)["wallgold"]
    assert spec.sell_fee.min_billable_mg == 400
    assert spec.buy_fee.min_billable_mg == 0


def test_miligold_commission_is_billed_in_gold():
    spec = load_platforms(CONFIG)["miligold"]
    assert spec.buy_fee.basis is FeeBasis.GOLD
    assert spec.sell_fee.basis is FeeBasis.GOLD


def test_only_goldika_is_genuinely_two_sided():
    # Measured live: MilliGold, MelliGold, WallGold and Talasea all return the
    # same number for buy and sell and carry their spread in the fee. Declaring
    # otherwise would let the strategy compare their mid against Goldika's real
    # ask as though the spread did not exist.
    specs = load_platforms(CONFIG)
    assert specs["goldika"].can(Capability.TWO_SIDED_QUOTE)
    for name in ("miligold", "melligold", "wallgold", "talasea"):
        assert not specs[name].can(Capability.TWO_SIDED_QUOTE)
    assert specs["miligold"].can(Capability.INVOICE_FLOW)


def test_talasea_fee_is_double_the_others():
    specs = load_platforms(CONFIG)
    assert specs["talasea"].buy_fee.rate == Decimal("0.01")
    assert specs["miligold"].buy_fee.rate == Decimal("0.005")


def test_miligold_is_switched_off():
    # Disabled on the owner's judgement that its quote is not executable, so it
    # must not reach either the scan or the router.
    spec = load_platforms(CONFIG)["miligold"]
    assert not spec.enabled
    assert not spec.tradable


def test_talasea_scans_but_cannot_trade():
    # Its price endpoint is public so it feeds the recorder, but no order has
    # ever gone through it, so it must not be routed to.
    spec = load_platforms(CONFIG)["talasea"]
    assert spec.enabled
    assert not spec.verified
    assert not spec.tradable


def test_melligold_is_tradable_after_a_real_round_trip():
    spec = load_platforms(CONFIG)["melligold"]
    assert spec.tradable
    # The floors differ by side, which the invoices established.
    assert spec.buy_fee.min_billable_mg == 200
    assert spec.sell_fee.min_billable_mg == 400


def test_goldika_units_are_settled_and_it_is_tradable():
    # Real orders 1829431 and 1829432 established that both sides take whole
    # milligrams, which is what cleared it to trade.
    spec = load_platforms(CONFIG)["goldika"]
    assert spec.enabled
    assert spec.verified
    assert spec.tradable
    assert spec.limits.step_mg == 1
    assert spec.limits.min_order_mg == 1


def test_goldika_charges_nothing_beyond_its_spread():
    # Buying 5mg cost the quoted price to the rial, and selling 5mg returned it.
    # The 1.2% that used to sit here was double-counting the spread.
    spec = load_platforms(CONFIG)["goldika"]
    assert spec.buy_fee.rate == 0
    assert spec.sell_fee.rate == 0


def test_rate_outside_unit_interval_is_rejected(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(
        '[platforms.x]\nadapter = "a:B"\n[platforms.x.buy_fee]\nrate = "1.5"\n'
    )
    with pytest.raises(ConfigError, match="not a fraction"):
        load_platforms(bad)


def test_min_order_off_the_step_grid_is_rejected(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(
        '[platforms.x]\nadapter = "a:B"\n'
        "[platforms.x.limits]\nmin_order_mg = 15\nstep_mg = 10\n"
    )
    with pytest.raises(ConfigError, match="not a multiple"):
        load_platforms(bad)


def test_missing_adapter_is_rejected(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[platforms.x]\nenabled = true\n")
    with pytest.raises(ConfigError, match="missing adapter"):
        load_platforms(bad)


def test_talasea_fee_matches_what_the_venue_reports():
    # /account/getUserData and /market/getGoldPrice both report fee 0.01.
    spec = load_platforms(CONFIG)["talasea"]
    assert spec.buy_fee.rate == Decimal("0.01")
    assert spec.sell_fee.rate == Decimal("0.01")
