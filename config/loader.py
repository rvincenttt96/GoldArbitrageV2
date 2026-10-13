"""Turn `platforms.toml` into `PlatformSpec` objects."""

from __future__ import annotations

import tomllib
from decimal import Decimal
from pathlib import Path

from core.platform import (
    Capability,
    FeeBasis,
    FeeSpec,
    LimitSpec,
    PlatformSpec,
    TreasurySpec,
)

DEFAULT_CONFIG = Path(__file__).with_name("platforms.toml")


class ConfigError(ValueError):
    """Raised when the venue registry cannot be trusted.

    Every failure here is fatal by design. A misread fee or a silently dropped
    limit produces a profit estimate that looks fine and is wrong, so there is no
    safe default to fall back to.
    """


def _fee(raw: dict, where: str) -> FeeSpec:
    try:
        basis = FeeBasis(raw.get("basis", "cash"))
    except ValueError as exc:
        raise ConfigError(f"{where}: unknown fee basis {raw.get('basis')!r}") from exc

    rate = Decimal(str(raw.get("rate", "0")))
    if rate < 0 or rate >= 1:
        raise ConfigError(f"{where}: rate {rate} is not a fraction between 0 and 1")

    return FeeSpec(
        rate=rate,
        basis=basis,
        min_billable_mg=int(raw.get("min_billable_mg", 0)),
        fixed_tmn=Decimal(str(raw.get("fixed_tmn", "0"))),
    )


def _limits(raw: dict, where: str) -> LimitSpec:
    limits = LimitSpec(
        min_order_mg=int(raw.get("min_order_mg", 1)),
        max_order_mg=(int(raw["max_order_mg"]) if "max_order_mg" in raw else None),
        step_mg=int(raw.get("step_mg", 1)),
    )
    if limits.step_mg < 1:
        raise ConfigError(f"{where}: step_mg must be at least 1")
    if limits.min_order_mg % limits.step_mg:
        raise ConfigError(
            f"{where}: min_order_mg {limits.min_order_mg} is not a multiple of "
            f"step_mg {limits.step_mg}, so the smallest legal order is ambiguous"
        )
    return limits


def _treasury(raw: dict, where: str) -> TreasurySpec:
    spec = TreasurySpec(
        min_cash_tmn=Decimal(str(raw.get("min_cash_tmn", "0"))),
        min_gold_mg=int(raw.get("min_gold_mg", 0)),
        target_cash_tmn=Decimal(str(raw.get("target_cash_tmn", "0"))),
        target_gold_mg=int(raw.get("target_gold_mg", 0)),
        surplus_cash_tmn=(
            Decimal(str(raw["surplus_cash_tmn"])) if "surplus_cash_tmn" in raw else None
        ),
        surplus_gold_mg=(
            int(raw["surplus_gold_mg"]) if "surplus_gold_mg" in raw else None
        ),
    )
    if spec.target_cash_tmn and spec.target_cash_tmn < spec.min_cash_tmn:
        raise ConfigError(f"{where}: target_cash_tmn is below min_cash_tmn")
    if spec.target_gold_mg and spec.target_gold_mg < spec.min_gold_mg:
        raise ConfigError(f"{where}: target_gold_mg is below min_gold_mg")
    return spec


def load_platforms(path: Path | None = None) -> dict[str, PlatformSpec]:
    """Load every venue in the registry, enabled or not."""
    path = path or DEFAULT_CONFIG
    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    specs: dict[str, PlatformSpec] = {}

    for name, body in raw.get("platforms", {}).items():
        where = f"platforms.{name}"

        try:
            capabilities = frozenset(
                Capability(c) for c in body.get("capabilities", [])
            )
        except ValueError as exc:
            raise ConfigError(f"{where}: {exc}") from exc

        if "adapter" not in body:
            raise ConfigError(f"{where}: missing adapter")

        specs[name] = PlatformSpec(
            name=name,
            display_name=body.get("display_name", name),
            enabled=bool(body.get("enabled", False)),
            adapter=body["adapter"],
            buy_fee=_fee(body.get("buy_fee", {}), f"{where}.buy_fee"),
            sell_fee=_fee(body.get("sell_fee", {}), f"{where}.sell_fee"),
            limits=_limits(body.get("limits", {}), f"{where}.limits"),
            capabilities=capabilities,
            quote_ttl_seconds=float(body.get("quote_ttl_seconds", 30.0)),
            verified=bool(body.get("verified", False)),
            treasury=_treasury(body.get("treasury", {}), f"{where}.treasury"),
        )

    if not specs:
        raise ConfigError(f"{path}: no platforms defined")

    return specs
