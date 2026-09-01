from decimal import Decimal
from pathlib import Path

from config.loader import load_platforms
from core.models import Inventory, utcnow
from services.treasury import (
    Asset,
    find_shortfalls,
    format_alert,
    plan_transfers,
)

SPECS = load_platforms(Path(__file__).resolve().parents[1] / "config" / "platforms.toml")


def inv(name, cash, gold_mg):
    return Inventory(name, Decimal(cash), gold_mg, utcnow())


# The balances actually observed on 2026-09-01, after selling 0.5g on WallGold.
REAL = {
    "wallgold": inv("wallgold", 10_985_795, 3_699),
    "melligold": inv("melligold", 500_000, 0),
    "goldika": inv("goldika", 0, 0),
    "talasea": inv("talasea", 0, 0),
}


def test_it_spots_the_real_shortfalls():
    short = find_shortfalls(SPECS, REAL)
    flagged = {(s.platform, s.asset) for s in short}
    assert ("melligold", Asset.CASH) in flagged
    assert ("melligold", Asset.GOLD) in flagged
    # WallGold has plenty of gold, so only its cash should be marginal.
    assert ("wallgold", Asset.GOLD) not in flagged


def test_shortfall_says_how_much_is_missing():
    short = find_shortfalls(SPECS, REAL)
    cash = next(s for s in short if s.platform == "melligold" and s.asset is Asset.CASH)
    assert cash.missing == Decimal(10_500_000)
    # Topping up only to the minimum invites the same alert next trade.
    assert cash.to_target > cash.missing


def test_transfers_name_a_source_and_a_destination():
    donors = {
        "wallgold": inv("wallgold", 40_000_000, 3_699),
        "melligold": inv("melligold", 500_000, 1_000),
    }
    transfers = plan_transfers(SPECS, donors)
    assert transfers
    move = transfers[0]
    assert move.source == "wallgold"
    assert move.destination == "melligold"
    assert "withdraw" in move.describe()
    assert "deposit to melligold" in move.describe()


def test_no_transfer_is_invented_when_nobody_has_a_surplus():
    # Everyone is at or below target, so there is nothing to move.
    assert plan_transfers(SPECS, REAL) == []


def test_gold_shortfalls_get_no_transfer_and_the_message_says_why():
    short = find_shortfalls(SPECS, REAL)
    transfers = plan_transfers(SPECS, REAL, short)
    assert not any(t.asset is Asset.GOLD for t in transfers)

    text = format_alert(short, transfers)
    assert "Gold cannot be transferred" in text


def test_a_healthy_book_produces_no_alert():
    healthy = {
        name: inv(name, 30_000_000, 2_000)
        for name in ("wallgold", "melligold", "goldika", "talasea")
    }
    assert find_shortfalls(SPECS, healthy) == []
    assert format_alert([], []) == ""


def test_alert_lists_the_concrete_instruction():
    donors = {
        "wallgold": inv("wallgold", 40_000_000, 3_699),
        "melligold": inv("melligold", 500_000, 1_000),
    }
    short = find_shortfalls(SPECS, donors)
    text = format_alert(short, plan_transfers(SPECS, donors, short))
    assert "TREASURY ALERT" in text
    assert "Suggested transfers" in text
    assert "melligold" in text
