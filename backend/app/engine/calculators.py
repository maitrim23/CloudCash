"""Cost calculators for EC2 (+EBS), S3 and RDS.

Every function takes a validated line item + a PriceStore and returns an
ItemResult made of Components. A Component is one line of the bill with the
arithmetic spelled out in `explain`, mirroring the calculator's
`calculationString` feature.

Rounding rule (modelled on the calculator, which formats each tier amount and
each service subtotal to 2 decimals): each component is rounded to cents, an
item is the sum of its rounded components, the estimate is the sum of items,
so every number on screen adds up exactly. (That the calculator rounds *every*
service per component is an assumption, not something we verified.)
"""

from __future__ import annotations

from decimal import Decimal

from ..pricing.store import PriceNotFound, PriceStore
from ..schemas import (
    Component,
    EbsVolume,
    DataTransferItem,
    Ec2Item,
    ItemResult,
    Pricing,
    RdsItem,
    S3Item,
    Usage,
)
from .constants import AVG_WEEKS_IN_MONTH, HOURS_IN_MONTH, MONTHS_IN_YEAR
from .money import D, fmt, fmt_rate, round_money
from .tiers import Tier, tiered_cost

ZERO = Decimal(0)

# Share of a Savings Plan's total cost paid at purchase for "Partial Upfront".
# AWS describes partial upfront as "50% or more"; the console's default is exactly half.
SP_PARTIAL_UPFRONT_SHARE = Decimal("0.5")
SP_OFFERING = {"compute": "compute", "ec2_instance": "ec2instance"}
SP_LABEL = {"compute": "Compute Savings Plan", "ec2_instance": "EC2 Instance Savings Plan"}

PAYMENT_LABEL = {
    "no_upfront": "No Upfront",
    "partial_upfront": "Partial Upfront",
    "all_upfront": "All Upfront",
}


# ------------------------------------------------------------- utilities ---
def _comp(label: str, quantity: Decimal | str, unit: str, monthly: Decimal, upfront: Decimal = ZERO, explain: list[str] | None = None) -> Component:
    return Component(
        label=label,
        quantity=quantity if isinstance(quantity, str) else fmt_rate(quantity),
        unit=unit,
        monthly=fmt(monthly),
        upfront=fmt(upfront),
        explain=explain or [],
    )


def _finish(item, summary: str, components: list[Component], commitment_months: int, warnings: list[str]) -> ItemResult:
    monthly = sum((D(c.monthly) for c in components), ZERO)
    upfront = sum((D(c.upfront) for c in components), ZERO)
    effective = monthly + (upfront / commitment_months if commitment_months else ZERO)
    return ItemResult(
        name=item.name,
        type=item.type,
        region=item.region,
        summary=summary,
        components=components,
        monthly=fmt(monthly),
        upfront=fmt(upfront),
        first_12_months=fmt(monthly * MONTHS_IN_YEAR + upfront),
        effective_monthly=fmt(effective),
        warnings=warnings,
    )


def error_result(item, message: str) -> ItemResult:
    return ItemResult(
        name=item.name, type=item.type, region=item.region, summary=message, components=[],
        monthly="0.00", upfront="0.00", first_12_months="0.00", effective_monthly="0.00", error=message,
    )


def hours_per_month(usage: Usage, pricing: Pricing) -> tuple[Decimal, str]:
    """Hours an instance is billed per month."""
    if pricing.model in ("reserved", "savings_plan"):
        return HOURS_IN_MONTH, "Committed capacity is billed for every hour (730 h/month)"
    if usage.mode == "percent_month":
        hours = HOURS_IN_MONTH * usage.percent / 100
        return hours, f"{fmt_rate(usage.percent)}% of 730 h/month"
    if usage.mode == "hours_per_day":
        hours = usage.hours_per_day * usage.days_per_week * AVG_WEEKS_IN_MONTH
        return hours, f"{fmt_rate(usage.hours_per_day)} h/day x {fmt_rate(usage.days_per_week)} days/week x {AVG_WEEKS_IN_MONTH} weeks/month"
    return HOURS_IN_MONTH, "always on (730 h/month)"


# ------------------------------------------------- instance (EC2 + RDS) ----
def _instance_component(
    store: PriceStore, service: str, family: str, key: str, region: str, label: str,
    quantity: int, pricing: Pricing, usage: Usage, offering: str,
) -> tuple[Component, int]:
    hours, hours_note = hours_per_month(usage, pricing)
    if pricing.model == "on_demand":
        rate = store.single_price(service, region, family, key, unit="Hrs", term="OnDemand")
        monthly = quantity * hours * rate.price
        explain = [
            f"Hours per month: {hours_note} = {fmt_rate(round_money(hours, 4))} h",
            f"{quantity} instance(s) x {fmt_rate(round_money(hours, 4))} h x {fmt_rate(rate.price)} USD/h = {fmt(monthly)} USD",
        ]
        return _comp(label, Decimal(quantity), "instances", round_money(monthly), explain=explain), 0

    lease = pricing.term
    pay = PAYMENT_LABEL[pricing.payment]
    if pricing.model == "savings_plan":
        return _savings_plan_component(store, service, family, key, region, label, quantity, pricing)
    try:
        hourly = store.single_price(service, region, family, key, unit="Hrs", term="Reserved", lease=lease, offering=offering, payment=pay)
    except PriceNotFound:
        raise PriceNotFound(f"No {offering} {lease} {pay} Reserved price for this configuration in {region}")
    upfront_rates = [r for r in store.rates(service, region, family, key, term="Reserved", lease=lease, offering=offering, payment=pay) if r.unit == "Quantity"]
    upfront_fee = upfront_rates[0].price if upfront_rates else ZERO
    monthly = quantity * HOURS_IN_MONTH * hourly.price
    upfront = quantity * upfront_fee
    months = 12 * int(lease[0])
    explain = [
        f"{offering.title()} Reserved, {lease}, {pay}",
        f"Recurring: {quantity} x 730 h x {fmt_rate(hourly.price)} USD/h = {fmt(monthly)} USD per month",
        f"Upfront: {quantity} x {fmt_rate(upfront_fee)} USD = {fmt(upfront)} USD (paid once)",
        f"Effective monthly = {fmt(monthly)} + {fmt(upfront)} / {months} months",
    ]
    return _comp(label, Decimal(quantity), "instances", round_money(monthly), round_money(upfront), explain), months


def _savings_plan_component(store: PriceStore, service: str, family: str, key: str, region: str, label: str, quantity: int, pricing: Pricing) -> tuple[Component, int]:
    """Savings Plans: a $/hour commitment priced at a discounted *effective* rate.

    The published rate already includes the amortised upfront payment, so
        effective monthly = quantity x 730 x rate           (same for all 3 payment options)
    and the payment option only decides how that total is *paid*:
        No Upfront      : all monthly
        Partial Upfront : 50% at purchase, 50% spread monthly
        All Upfront     : 100% at purchase
    """
    if service != "ec2":
        raise PriceNotFound("Savings Plans apply to EC2 instances only (RDS uses Reserved Instances)")
    offering = SP_OFFERING[pricing.sp_type]
    pay = PAYMENT_LABEL[pricing.payment]
    try:
        rate = store.single_price(service, region, family, key, unit="Hrs", term="SavingsPlan", lease=pricing.term, offering=offering, payment=pay)
    except PriceNotFound:
        raise PriceNotFound(f"No {SP_LABEL[pricing.sp_type]} {pricing.term} {pay} price for this instance in {region}")
    years = int(pricing.term[0])
    months = 12 * years
    effective = quantity * HOURS_IN_MONTH * rate.price
    share = {"no_upfront": ZERO, "partial_upfront": SP_PARTIAL_UPFRONT_SHARE, "all_upfront": Decimal(1)}[pricing.payment]
    upfront = effective * months * share
    monthly = effective * (1 - share)
    explain = [
        f"{SP_LABEL[pricing.sp_type]}, {pricing.term}, {pay}",
        f"Effective cost: {quantity} x 730 h x {fmt_rate(rate.price)} USD/h = {fmt(effective)} USD per month",
        f"Upfront share {fmt_rate(share * 100)}% x {fmt(effective)} x {months} months = {fmt(upfront)} USD (paid once)",
        f"Recurring: {fmt(effective)} x {fmt_rate((1 - share) * 100)}% = {fmt(monthly)} USD per month",
    ]
    return _comp(label, Decimal(quantity), "instances", round_money(monthly), round_money(upfront), explain), months


# ---------------------------------------------------------------- EBS ------
# Free baselines included in the gp3 price (AWS documentation).
GP3_FREE_IOPS = Decimal(3000)
GP3_FREE_THROUGHPUT_MBPS = Decimal(125)
# io2 IOPS are billed in three graduated tiers; AWS publishes one SKU per tier
# without the boundaries in the price list, so they live here (AWS EBS pricing page).
IO2_TIER_BOUNDS = (Decimal(32000), Decimal(64000))


def _ebs_components(store: PriceStore, region: str, vol: EbsVolume, instances: int, idx: int, warnings: list[str]) -> list[Component]:
    out: list[Component] = []
    tag = f"EBS volume {idx} ({vol.volume_type}, {fmt_rate(vol.size_gb)} GB)"
    count = Decimal(instances)

    storage = store.single_price("ec2", region, "ebs_storage", vol.volume_type, unit=None)
    cost = vol.size_gb * storage.price * count
    out.append(_comp(f"{tag} - storage", vol.size_gb * count, "GB-month", round_money(cost), explain=[
        f"{instances} instance(s) x {fmt_rate(vol.size_gb)} GB x {fmt_rate(storage.price)} USD/GB-month = {fmt(cost)} USD"]))

    if vol.volume_type == "gp3":
        iops = vol.iops if vol.iops is not None else GP3_FREE_IOPS
        extra = max(iops - GP3_FREE_IOPS, ZERO)
        if extra > 0:
            p = store.single_price("ec2", region, "ebs_iops", "gp3")
            c = extra * p.price * count
            out.append(_comp(f"{tag} - extra IOPS", extra * count, "IOPS-month", round_money(c), explain=[
                f"({fmt_rate(iops)} provisioned - 3000 free) = {fmt_rate(extra)} IOPS x {instances} x {fmt_rate(p.price)} USD = {fmt(c)} USD"]))
        thr = vol.throughput_mbps if vol.throughput_mbps is not None else GP3_FREE_THROUGHPUT_MBPS
        extra_t = max(thr - GP3_FREE_THROUGHPUT_MBPS, ZERO)
        if extra_t > 0:
            p = store.single_price("ec2", region, "ebs_throughput", "gp3")
            per_mbps = p.price / 1024  # AWS lists the price per GiB/s-month
            c = extra_t * per_mbps * count
            out.append(_comp(f"{tag} - extra throughput", extra_t * count, "MB/s-month", round_money(c), explain=[
                f"({fmt_rate(thr)} provisioned - 125 free) = {fmt_rate(extra_t)} MB/s x {instances} x ({fmt_rate(p.price)} / 1024) USD = {fmt(c)} USD"]))
    elif vol.volume_type == "io1":
        iops = vol.iops
        if iops is None:
            iops = Decimal(3000)
            warnings.append(f"{tag}: no IOPS given, assumed 3000")
        p = store.single_price("ec2", region, "ebs_iops", "io1")
        c = iops * p.price * count
        out.append(_comp(f"{tag} - provisioned IOPS", iops * count, "IOPS-month", round_money(c), explain=[
            f"{fmt_rate(iops)} IOPS x {instances} x {fmt_rate(p.price)} USD = {fmt(c)} USD"]))
    elif vol.volume_type == "io2":
        iops = vol.iops
        if iops is None:
            iops = Decimal(3000)
            warnings.append(f"{tag}: no IOPS given, assumed 3000")
        t1, t2, t3 = (store.single_price("ec2", region, "ebs_iops", f"io2:tier{n}").price for n in (1, 2, 3))
        tiers = [Tier(ZERO, IO2_TIER_BOUNDS[0], t1), Tier(IO2_TIER_BOUNDS[0], IO2_TIER_BOUNDS[1], t2), Tier(IO2_TIER_BOUNDS[1], None, t3)]
        res = tiered_cost(tiers, iops)
        c = res.total * count
        out.append(_comp(f"{tag} - provisioned IOPS", iops * count, "IOPS-month", round_money(c),
                         explain=res.explain("IOPS") + [f"x {instances} instance(s) = {fmt(c)} USD"]))

    if vol.snapshots_per_month > 0:
        # Recovered from the calculator's `snapShotMaths` command:
        #   initial     = storage x price
        #   each        = changed x price
        #   discount    = each / 2          (the average snapshot is half-changed)
        #   incremental = discount x frequency
        #   total       = initial + incremental
        sp = store.single_price("ec2", region, "ebs_snapshot", "standard").price
        initial = vol.size_gb * sp
        each = vol.snapshot_changed_gb * sp
        discount = each / 2
        incremental = discount * vol.snapshots_per_month
        total = (initial + incremental) * count
        out.append(_comp(f"{tag} - snapshots", vol.size_gb * count, "GB-month", round_money(total), explain=[
            f"Initial snapshot: {fmt_rate(vol.size_gb)} GB x {fmt_rate(sp)} = {fmt(initial, 4)} USD",
            f"Each later snapshot: {fmt_rate(vol.snapshot_changed_gb)} GB changed x {fmt_rate(sp)} = {fmt(each, 4)} USD, halved = {fmt(discount, 4)} USD",
            f"Incremental: {fmt(discount, 4)} x {vol.snapshots_per_month} snapshots = {fmt(incremental, 4)} USD",
            f"({fmt(initial, 4)} + {fmt(incremental, 4)}) x {instances} instance(s) = {fmt(total)} USD"]))
    return out


# ---------------------------------------------------------------- EC2 ------
def calc_ec2(item: Ec2Item, store: PriceStore) -> ItemResult:
    key = f"{item.instance_type}|{item.os}"
    spec = store.product("ec2", item.region, "ec2_instance", key)  # raises PriceNotFound
    warnings: list[str] = []
    label = f"{item.instance_type} ({item.os})"
    comp, months = _instance_component(
        store, "ec2", "ec2_instance", key, item.region, f"EC2 {label}", item.quantity,
        item.pricing, item.usage, item.pricing.offering_class,
    )
    components = [comp]
    for i, vol in enumerate(item.ebs, start=1):
        components.extend(_ebs_components(store, item.region, vol, item.quantity, i, warnings))
    if item.pricing.model == "on_demand" and item.usage.mode != "always" and item.ebs:
        warnings.append("EBS volumes are billed for the whole month even when the instance is stopped.")
    if item.pricing.model == "on_demand":
        purchase = "On-Demand"
    elif item.pricing.model == "savings_plan":
        purchase = f"{SP_LABEL[item.pricing.sp_type]} {item.pricing.term} {PAYMENT_LABEL[item.pricing.payment]}"
    else:
        purchase = f"{item.pricing.offering_class.title()} RI {item.pricing.term} {PAYMENT_LABEL[item.pricing.payment]}"
    summary = f"{item.quantity} x {label}, {spec.get('vcpu')} vCPU, {spec.get('memory')}, {purchase}"
    return _finish(item, summary, components, months, warnings)


# ----------------------------------------------------------------- S3 ------
# storage_class -> (price-list volumeType, PUT-class key, GET-class key, retrieval key)
S3_CLASSES = {
    "standard": ("Standard", "Requests-Tier1", "Requests-Tier2", None),
    "standard_ia": ("Standard - Infrequent Access", "Requests-SIA-Tier1", "Requests-SIA-Tier2", "Retrieval-SIA"),
    "onezone_ia": ("One Zone - Infrequent Access", "Requests-ZIA-Tier1", "Requests-ZIA-Tier2", "Retrieval-ZIA"),
    "glacier_ir": ("Glacier Instant Retrieval", "Requests-GIR-Tier1", "Requests-GIR-Tier2", "Retrieval-GIR"),
}
S3_LABELS = {
    "standard": "S3 Standard", "standard_ia": "S3 Standard-IA",
    "onezone_ia": "S3 One Zone-IA", "glacier_ir": "S3 Glacier Instant Retrieval",
}


def calc_s3(item: S3Item, store: PriceStore) -> ItemResult:
    volume_type, put_key, get_key, retrieval_key = S3_CLASSES[item.storage_class]
    label = S3_LABELS[item.storage_class]
    components: list[Component] = []

    tiers = store.tiers("s3", item.region, "s3_storage", volume_type)
    res = tiered_cost(tiers, item.storage_gb)
    components.append(_comp(f"{label} - storage", item.storage_gb, "GB-month", round_money(res.total),
                            explain=[f"Tiered price for {fmt_rate(item.storage_gb)} GB:"] + res.explain("GB")))

    for qty, key, what in ((item.put_requests, put_key, "PUT, COPY, POST, LIST requests"), (item.get_requests, get_key, "GET, SELECT and other requests")):
        if qty > 0:
            p = store.single_price("s3", item.region, "s3_request", key)
            c = qty * p.price
            components.append(_comp(f"{label} - {what}", qty, "requests", round_money(c), explain=[
                f"{fmt_rate(qty)} requests x {fmt_rate(p.price)} USD = {fmt(c)} USD"]))
    if item.retrieval_gb > 0:
        if retrieval_key is None:
            raise PriceNotFound("S3 Standard has no data-retrieval charge")
        p = store.single_price("s3", item.region, "s3_request", retrieval_key)
        c = item.retrieval_gb * p.price
        components.append(_comp(f"{label} - data retrieval", item.retrieval_gb, "GB", round_money(c), explain=[
            f"{fmt_rate(item.retrieval_gb)} GB x {fmt_rate(p.price)} USD = {fmt(c)} USD"]))

    warnings = ["Data transfer out of S3 and management features (inventory, analytics) are not included."]
    return _finish(item, f"{label}, {fmt_rate(item.storage_gb)} GB", components, 0, warnings)


# ---------------------------------------------------------------- RDS ------
RDS_STORAGE_TYPE = {  # our name -> (storage volumeType in the price list, IOPS family kind)
    "gp2": ("General Purpose", None),
    "gp3": ("General Purpose-GP3", "gp3"),
    "io1": ("Provisioned IOPS", "io1"),
    "io2": ("Provisioned IOPS-IO2", "io2"),
}


def calc_rds(item: RdsItem, store: PriceStore) -> ItemResult:
    deployment = "Multi-AZ" if item.deployment == "multi_az" else "Single-AZ"
    key = "|".join([item.instance_type, item.engine, item.edition, item.license_model, deployment])
    spec = store.product("rds", item.region, "rds_instance", key)
    warnings: list[str] = []
    label = f"{item.instance_type} {item.engine}{' ' + item.edition if item.edition else ''} ({deployment})"
    comp, months = _instance_component(
        store, "rds", "rds_instance", key, item.region, f"RDS {label}", item.quantity,
        item.pricing, item.usage, "standard",
    )
    components = [comp]
    count = Decimal(item.quantity)

    # NOTE: Multi-AZ is NOT "double the Single-AZ price". AWS publishes a separate
    # SKU for Multi-AZ instances *and* for Multi-AZ storage; we look those up.
    volume_type, iops_kind = RDS_STORAGE_TYPE[item.storage_type]
    sp = store.single_price("rds", item.region, "rds_storage", f"{volume_type}|{deployment}|{item.engine}")
    c = item.storage_gb * sp.price * count
    components.append(_comp(f"RDS storage ({item.storage_type}, {deployment})", item.storage_gb * count, "GB-month", round_money(c), explain=[
        f"{item.quantity} instance(s) x {fmt_rate(item.storage_gb)} GB x {fmt_rate(sp.price)} USD/GB-month = {fmt(c)} USD"]))

    if item.storage_type in ("io1", "io2"):
        iops = item.iops if item.iops is not None else Decimal(1000)
        if item.iops is None:
            warnings.append("No IOPS given, assumed 1000")
        ip = store.single_price("rds", item.region, "rds_iops", f"{iops_kind}|{deployment}|{item.engine}")
        c = iops * ip.price * count
        components.append(_comp(f"RDS provisioned IOPS ({item.storage_type})", iops * count, "IOPS-month", round_money(c), explain=[
            f"{fmt_rate(iops)} IOPS x {item.quantity} x {fmt_rate(ip.price)} USD = {fmt(c)} USD"]))
    elif item.storage_type == "gp3" and item.iops:
        warnings.append("gp3 IOPS above the included baseline are not modelled.")

    warnings.append("Backup storage beyond the free allocation, data transfer and Performance Insights are not included.")
    purchase = "On-Demand" if item.pricing.model == "on_demand" else f"Reserved {item.pricing.term} {PAYMENT_LABEL[item.pricing.payment]}"
    summary = f"{item.quantity} x {label}, {spec.get('vcpu')} vCPU, {spec.get('memory')}, {purchase}"
    return _finish(item, summary, components, months, warnings)


# ------------------------------------------------------- data transfer -----
# AWS bills cross-AZ traffic $0.01/GB in EACH direction (sender and receiver), and the
# price file lists the single-direction rate. (AWS EC2 pricing page, "Data Transfer".)
CROSS_AZ_DIRECTIONS = Decimal(2)


def calc_dt(item: DataTransferItem, store: PriceStore) -> ItemResult:
    components: list[Component] = []
    warnings = ["Data transferred IN to AWS is free and is not shown."]

    if item.internet_out_gb > 0:
        tiers = store.tiers("dt", item.region, "dt_internet_out", "internet")
        billable = item.internet_out_gb
        explain: list[str] = []
        if item.apply_free_tier:
            free = store.single_price("dt", item.region, "dt_free", "internet_out")
            allowance = free.end if free.end is not None else ZERO
            free_used = min(billable, allowance)
            billable -= free_used
            explain.append(f"Free allowance: first {fmt_rate(allowance)} GB per month -> {fmt_rate(free_used)} GB free, {fmt_rate(billable)} GB billable")
            warnings.append("The free 100 GB is applied here; AWS gives it once per account, so keep a single data-transfer line with it enabled.")
        res = tiered_cost(tiers, billable)
        components.append(_comp("Data transfer out to the internet", item.internet_out_gb, "GB", round_money(res.total),
                                explain=explain + res.explain("GB")))

    if item.inter_region_gb > 0:
        if not item.destination_region:
            raise PriceNotFound("Choose a destination region for inter-region transfer")
        p = store.single_price("dt", item.region, "dt_interregion", item.destination_region)
        c = item.inter_region_gb * p.price
        components.append(_comp(f"Data transfer to {item.destination_region}", item.inter_region_gb, "GB", round_money(c), explain=[
            f"{fmt_rate(item.inter_region_gb)} GB x {fmt_rate(p.price)} USD = {fmt(c)} USD"]))

    if item.cross_az_gb > 0:
        p = store.single_price("dt", item.region, "dt_cross_az", "cross_az")
        c = item.cross_az_gb * p.price * CROSS_AZ_DIRECTIONS
        components.append(_comp("Data transfer between availability zones", item.cross_az_gb, "GB", round_money(c), explain=[
            f"{fmt_rate(item.cross_az_gb)} GB x {fmt_rate(p.price)} USD x 2 directions = {fmt(c)} USD"]))

    if not components:
        warnings.append("Enter an amount of data to price.")
    total_gb = item.internet_out_gb + item.inter_region_gb + item.cross_az_gb
    return _finish(item, f"{fmt_rate(total_gb)} GB transferred out of {item.region}", components, 0, warnings)
