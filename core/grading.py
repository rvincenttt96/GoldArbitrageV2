"""Signal grading and the capital that each grade is allowed to commit.

A single profit threshold forces one choice for two different questions: is this
worth doing, and how much should it be worth. Splitting them lets a thin
opportunity trade small instead of not trading at all, which raises the number
of fills without putting the same money behind a weak signal as a strong one.

Grades are ordered best to worst. Each carries the minimum net return that
qualifies for it and the share of available capital it may use.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Grade:
    name: str

    #: Minimum net return, as a fraction of cash deployed, to reach this grade.
    min_return: Decimal

    #: Share of otherwise-available capital this grade may commit.
    capital_fraction: Decimal

    def __str__(self) -> str:
        return (
            f"{self.name} (>={self.min_return * 100:.2f}%, "
            f"{self.capital_fraction * 100:.0f}% of capital)"
        )


class GradeLadder:
    """Maps a net return onto a grade, and a grade onto a position size."""

    def __init__(self, grades: list[Grade]):
        if not grades:
            raise ValueError("a grade ladder needs at least one grade")

        self.grades = sorted(grades, key=lambda g: g.min_return, reverse=True)

        # A ladder where a worse grade may deploy more capital than a better one
        # would quietly invert the whole point, so it is rejected outright
        # rather than left to surprise someone reading a fill later.
        for better, worse in zip(self.grades, self.grades[1:], strict=False):
            if worse.capital_fraction > better.capital_fraction:
                raise ValueError(
                    f"grade {worse.name} allows more capital than {better.name} "
                    "despite requiring a lower return"
                )

    @property
    def floor(self) -> Decimal:
        """The lowest return that earns any grade at all."""
        return self.grades[-1].min_return

    def classify(self, net_return: Decimal) -> Grade | None:
        """Best grade this return qualifies for, or None if it earns none."""
        for grade in self.grades:
            if net_return >= grade.min_return:
                return grade
        return None

    def __iter__(self):
        return iter(self.grades)

    def __len__(self) -> int:
        return len(self.grades)


#: Starting ladder. The floor sits above the cheapest possible round trip
#: (0.5% + 0.5% between the two cheapest venues) so that no grade can be earned
#: by a trade that only looks profitable because a fee was understated.
DEFAULT_LADDER = GradeLadder([
    Grade("A", Decimal("0.015"), Decimal("1.00")),
    Grade("B", Decimal("0.010"), Decimal("0.60")),
    Grade("C", Decimal("0.006"), Decimal("0.35")),
    Grade("D", Decimal("0.0035"), Decimal("0.15")),
])
