"""Tiered ("graduated") pricing.

Port of the calculator's ``tieredPricingMath`` command (see study.md). The
original walks the tiers in order:

    tier 0:                 used = clamp(min(end - start, qty), 0, ...)
    middle tier:            used = max(min(end - prevEnd, qty - prevEnd), 0)
    last tier (end = -1):   used = max(qty - prevEnd, 0)
    cost = sum(used * price)

which is the same thing as the cleaner formulation we implement here:

    used_in_tier = clamp(qty - tier.start, 0, tier.end - tier.start)

The two differ only if tiers have gaps/overlaps (the calculator's Storage Gateway
data has a 12500 -> 12501 gap), which never happens in the AWS price-list files
we ingest, so we validate contiguity instead of reproducing the quirk.
``tests/test_tiers.py`` checks both formulations against each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .money import D, fmt, fmt_rate


@dataclass(frozen=True)
class Tier:
    start: Decimal
    end: Decimal | None  # None == infinity (AWS "Inf", calculator's -1)
    price: Decimal


@dataclass(frozen=True)
class TierSlice:
    tier: Tier
    quantity: Decimal
    cost: Decimal


@dataclass(frozen=True)
class TierResult:
    total: Decimal
    slices: list[TierSlice]

    def explain(self, unit: str, currency: str = "USD") -> list[str]:
        return [
            f"{fmt_rate(s.quantity)} {unit} x {fmt_rate(s.tier.price)} {currency} = {fmt(s.cost)} {currency}"
            for s in self.slices
        ]


def validate_tiers(tiers: list[Tier]) -> None:
    """Same sanity check the calculator applies (data-quality gate)."""
    if not tiers:
        raise ValueError("no tiers")
    if tiers[0].start != 0:
        raise ValueError("first tier must start at 0")
    for prev, nxt in zip(tiers, tiers[1:]):
        if prev.end is None or prev.end != nxt.start:
            raise ValueError("tiers must be contiguous")
    if tiers[-1].end is not None:
        raise ValueError("last tier must be open-ended")


def tiered_cost(tiers: list[Tier], quantity: Decimal | int | float | str) -> TierResult:
    qty = D(quantity)
    if qty < 0:
        raise ValueError("quantity cannot be negative")
    ordered = sorted(tiers, key=lambda t: t.start)
    validate_tiers(ordered)

    slices: list[TierSlice] = []
    total = Decimal(0)
    for tier in ordered:
        upper = qty if tier.end is None else min(qty, tier.end)
        used = max(upper - tier.start, Decimal(0))
        if used > 0:
            cost = used * tier.price
            total += cost
            slices.append(TierSlice(tier=tier, quantity=used, cost=cost))
    return TierResult(total=total, slices=slices)


def tiered_cost_calculator_port(tiers: list[Tier], quantity: Decimal) -> Decimal:
    """Literal port of the calculator's loop, kept for cross-checking in tests."""
    qty = D(quantity)
    total = Decimal(0)
    for n, tier in enumerate(tiers):
        start, end, price = tier.start, tier.end, tier.price
        if n == 0:
            span = Decimal("Infinity") if end is None else end - start
            used = max(min(span, qty), Decimal(0))
        elif end is not None:
            prev_end = tiers[n - 1].end
            used = max(min(end - prev_end, qty - prev_end), Decimal(0))
        else:
            prev_end = tiers[n - 1].end
            used = max(qty - prev_end, Decimal(0))
        total += used * price
    return total
