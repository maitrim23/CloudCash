"""Scenario -> EstimateResult, and scenario comparison."""

from __future__ import annotations

from decimal import Decimal

from ..pricing.store import PriceNotFound, PriceStore
from ..schemas import (
    CompareResult,
    DataTransferItem,
    Ec2Item,
    EstimateResult,
    ItemResult,
    RdsItem,
    S3Item,
    Scenario,
    ScenarioDiff,
)
from .calculators import calc_dt, calc_ec2, calc_rds, calc_s3, error_result
from .constants import MONTHS_IN_YEAR
from .money import D, fmt, round_money

ASSUMPTIONS = [
    "List prices in USD from the public AWS price list: no discounts, taxes, credits or Free Tier.",
    "A month is 730 hours (8,760 / 12); a year is 12 such months.",
    "On-Demand instances are billed only for the hours they run; EBS and RDS storage are billed for the whole month.",
    "Reserved instances are billed every hour of the term. Effective monthly spreads any upfront fee evenly over the term.",
    "Each line is rounded to cents; item and estimate totals are sums of the rounded lines.",
    "This is an estimate, not a bill. Several secondary charges (backups beyond the free allocation, Performance Insights, NAT gateways, CDN) are not modelled.",
]

_CALCULATORS = {Ec2Item: calc_ec2, S3Item: calc_s3, RdsItem: calc_rds, DataTransferItem: calc_dt}
_SERVICE = {Ec2Item: "ec2", S3Item: "s3", RdsItem: "rds", DataTransferItem: "dt"}


def calculate_item(item, store: PriceStore) -> ItemResult:
    try:
        return _CALCULATORS[type(item)](item, store)
    except PriceNotFound as exc:
        # One unsupported combination must not sink the whole estimate.
        return error_result(item, str(exc))


def calculate(scenario: Scenario, store: PriceStore) -> EstimateResult:
    results = [calculate_item(item, store) for item in scenario.items]
    ok = [r for r in results if r.error is None]
    monthly = sum((D(r.monthly) for r in ok), Decimal(0))
    upfront = sum((D(r.upfront) for r in ok), Decimal(0))
    effective = sum((D(r.effective_monthly) for r in ok), Decimal(0))

    dates: dict[str, str] = {}
    for item in scenario.items:
        service = _SERVICE[type(item)]
        when = store.publication_date(service, item.region)
        if when:
            dates[f"{service}/{item.region}"] = when[:10]

    return EstimateResult(
        name=scenario.name,
        items=results,
        monthly=fmt(monthly),
        yearly=fmt(monthly * MONTHS_IN_YEAR),
        upfront=fmt(upfront),
        first_12_months=fmt(monthly * MONTHS_IN_YEAR + upfront),
        effective_monthly=fmt(effective),
        price_list_dates=dates,
        assumptions=ASSUMPTIONS,
    )


def compare(scenarios: list[Scenario], store: PriceStore) -> CompareResult:
    """Compare on *effective monthly* cost so a 3-year all-upfront scenario and an
    on-demand one are measured on the same footing (upfront spread over its term)."""
    estimates = [calculate(s, store) for s in scenarios]
    base = D(estimates[0].effective_monthly)
    diffs: list[ScenarioDiff] = []
    for est in estimates:
        eff = D(est.effective_monthly)
        delta = eff - base
        pct = (delta / base * 100) if base else Decimal(0)
        diffs.append(
            ScenarioDiff(
                name=est.name,
                monthly=est.monthly,
                first_12_months=est.first_12_months,
                effective_monthly=est.effective_monthly,
                vs_baseline=fmt(delta),
                vs_baseline_pct=fmt(pct),
            )
        )
    cheapest = min(estimates, key=lambda e: D(e.effective_monthly)).name
    return CompareResult(baseline=estimates[0].name, scenarios=estimates, diffs=diffs, cheapest=cheapest)
