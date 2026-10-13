"""Selects which venues are live and hands back their adapters.

The registry is the only place that knows how to turn a spec into a client, so
turning a venue on or off is a config change rather than an edit to the bot.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from config.loader import ConfigError, load_platforms
from core.platform import Capability, PlatformSpec


@dataclass(frozen=True)
class Venue:
    """A venue's spec paired with its live client."""

    spec: PlatformSpec
    client: object

    @property
    def name(self) -> str:
        return self.spec.name


def _import_adapter(target: str) -> type:
    """Resolve a `package.module:ClassName` reference."""
    module_name, _, class_name = target.partition(":")
    if not class_name:
        raise ConfigError(f"adapter {target!r} must be 'module:ClassName'")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ConfigError(f"adapter {target!r} is not importable: {exc}") from exc
    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise ConfigError(f"adapter {target!r}: {class_name} not found") from exc


class PlatformRegistry:
    """Holds the venues that are switched on for this run."""

    def __init__(self, venues: list[Venue]):
        self._venues = venues
        self._by_name = {v.name: v for v in venues}

    @classmethod
    def build(
        cls,
        credentials: dict[str, dict],
        *,
        config_path: Path | None = None,
        only: set[str] | None = None,
    ) -> PlatformRegistry:
        """Instantiate every enabled venue that we hold credentials for.

        `only` further narrows the selection, which is what a backtest or a
        single-venue smoke test uses to run against a subset without touching
        the config file.
        """
        specs = load_platforms(config_path)
        venues: list[Venue] = []

        for name, spec in specs.items():
            if not spec.enabled:
                continue
            if only is not None and name not in only:
                continue
            if name not in credentials:
                raise ConfigError(
                    f"platform {name!r} is enabled but no credentials were supplied"
                )

            adapter_cls = _import_adapter(spec.adapter)
            venues.append(Venue(spec=spec, client=adapter_cls(**credentials[name])))

        if not venues:
            raise ConfigError("no platforms are enabled; nothing to scan")

        return cls(venues)

    def __iter__(self) -> Iterator[Venue]:
        return iter(self._venues)

    def __len__(self) -> int:
        return len(self._venues)

    def __getitem__(self, name: str) -> Venue:
        return self._by_name[name]

    def get(self, name: str) -> Venue | None:
        return self._by_name.get(name)

    def all(self) -> list[Venue]:
        """Every enabled venue. These may be scanned."""
        return list(self._venues)

    def tradable(self) -> list[Venue]:
        """Venues cleared to place orders.

        Enabled-but-unverified venues are deliberately excluded: they contribute
        prices to the scan and to the recorder, but an opportunity that routes
        through one of them must never reach the executor.
        """
        return [v for v in self._venues if v.spec.tradable]

    def with_capability(self, capability: Capability) -> list[Venue]:
        return [v for v in self._venues if v.spec.can(capability)]

    def specs(self) -> dict[str, PlatformSpec]:
        return {v.name: v.spec for v in self._venues}


def describe(registry: PlatformRegistry) -> str:
    """One line per venue, for logging what the bot actually came up with."""
    lines = []
    for venue in registry:
        spec = venue.spec
        state = "tradable" if spec.tradable else "scan-only"
        caps = ",".join(sorted(c.value for c in spec.capabilities)) or "none"
        lines.append(f"{spec.display_name:<12} {state:<10} capabilities={caps}")
    return "\n".join(lines)


__all__ = ["PlatformRegistry", "Venue", "describe"]
