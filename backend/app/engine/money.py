"""Decimal helpers.

The AWS calculator does its arithmetic with decimal.js (arbitrary precision)
rather than IEEE floats. We do the same with Python's ``decimal`` so that
0.1 + 0.2 == 0.3 and totals match to the cent.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 40  # far more than any price x quantity needs

# Names copied from the calculator's `rounding` command:
#   standard -> ROUND_HALF_UP, roundUp -> ROUND_CEIL, roundDown -> ROUND_FLOOR
ROUNDING_MODES = {
    "standard": ROUND_HALF_UP,
    "round_up": ROUND_CEILING,
    "round_down": ROUND_FLOOR,
}

CENT = Decimal("0.01")


def D(value: object) -> Decimal:
    """Convert anything number-like to Decimal without float noise."""
    if isinstance(value, Decimal):
        return value
    # str() first so that float 0.1 becomes Decimal("0.1"), not 0.1000000000000000055...
    return Decimal(str(value))


def round_money(value: Decimal, places: int = 2, mode: str = "standard") -> Decimal:
    quantum = Decimal(1).scaleb(-places)
    return value.quantize(quantum, rounding=ROUNDING_MODES[mode])


def fmt(value: Decimal, places: int = 2) -> str:
    """Plain, non-scientific string used inside human-readable calculation text."""
    return format(round_money(value, places), "f")


def fmt_rate(value: Decimal) -> str:
    """Show a unit price with its natural precision (no trailing zeros)."""
    text = format(value.normalize(), "f")
    return text
