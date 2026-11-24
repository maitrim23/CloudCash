"""Hand-computed expectations against the synthetic price list (tests/fixtures.py).

Fixture prices: m5.large Linux $0.10/h (RI 1yr std: NoUp 0.06/h, Partial 0.03/h + 260, All 500);
gp3 $0.10/GB, extra IOPS $0.005, throughput $40.96/GiBps (= $0.04 per MB/s), snapshots $0.05/GB.
"""

from decimal import Decimal

import pytest

from app.engine.estimate import calculate, calculate_item
from app.schemas import (
    DataTransferItem, EbsVolume, Ec2Item, Pricing, RdsItem, S3Item, Scenario, Usage,
)

R = "ap-south-1"


def ec2(**kw):
    return Ec2Item(region=R, instance_type="m5.large", **kw)


def comps(res):
    return {c.label: c for c in res.components}


# ----------------------------------------------------------------- EC2 -----
def test_ec2_on_demand_always_on(store):
    res = calculate_item(ec2(quantity=2), store)
    assert res.monthly == "146.00"  # 2 x 730 x 0.10
    assert res.upfront == "0.00" and res.first_12_months == "1752.00"


def test_ec2_windows_costs_more(store):
    assert calculate_item(ec2(os="Windows"), store).monthly == "146.00"  # 730 x 0.20


def test_ec2_utilization_percent(store):
    res = calculate_item(ec2(usage=Usage(mode="percent_month", percent=Decimal(50))), store)
    assert res.monthly == "36.50"  # 365 h x 0.10


def test_ec2_utilization_hours_per_day_matches_730_when_full_time(store):
    full = calculate_item(ec2(usage=Usage(mode="hours_per_day", hours_per_day=Decimal(24), days_per_week=Decimal(7))), store)
    assert full.monthly == "73.00"  # 24 x 7 x 4.345238095238095 = 729.99999... h


def test_ec2_utilization_office_hours(store):
    res = calculate_item(ec2(usage=Usage(mode="hours_per_day", hours_per_day=Decimal(8), days_per_week=Decimal(5))), store)
    assert res.monthly == "17.38"  # 40 h/week x 4.345238095 = 173.809524 h x 0.10 = 17.3809...


def test_reserved_ignores_utilization(store):
    p = Pricing(model="reserved", term="1yr", payment="no_upfront")
    res = calculate_item(ec2(pricing=p, usage=Usage(mode="percent_month", percent=Decimal(10))), store)
    assert res.monthly == "43.80"  # always 730 h x 0.06


def test_reserved_partial_upfront_effective_monthly(store):
    p = Pricing(model="reserved", term="1yr", payment="partial_upfront")
    res = calculate_item(ec2(pricing=p), store)
    assert (res.monthly, res.upfront) == ("21.90", "260.00")
    assert res.first_12_months == "522.80"  # 21.90 x 12 + 260
    assert res.effective_monthly == "43.57"  # 21.90 + 260/12


def test_reserved_all_upfront(store):
    p = Pricing(model="reserved", term="1yr", payment="all_upfront")
    res = calculate_item(ec2(pricing=p), store)
    assert (res.monthly, res.upfront, res.effective_monthly) == ("0.00", "500.00", "41.67")


def test_unavailable_reserved_option_is_reported_not_raised(store):
    p = Pricing(model="reserved", term="3yr", payment="no_upfront")
    res = calculate_item(ec2(pricing=p), store)
    assert res.error and "3yr" in res.error and res.monthly == "0.00"


def test_unknown_instance_type_is_reported(store):
    res = calculate_item(Ec2Item(region=R, instance_type="zz9.huge"), store)
    assert res.error and "zz9.huge" in res.error


# ----------------------------------------------------------------- EBS -----
def test_ebs_gp3_baseline_includes_free_iops_and_throughput(store):
    res = calculate_item(ec2(ebs=[EbsVolume(volume_type="gp3", size_gb=Decimal(100))]), store)
    c = comps(res)
    assert c["EBS volume 1 (gp3, 100 GB) - storage"].monthly == "10.00"
    assert len(res.components) == 2  # EC2 + storage only: no extra IOPS/throughput lines


def test_ebs_gp3_extra_iops_and_throughput_multiplied_by_instances(store):
    vol = EbsVolume(volume_type="gp3", size_gb=Decimal(100), iops=Decimal(4000), throughput_mbps=Decimal(250))
    c = comps(calculate_item(ec2(quantity=2, ebs=[vol]), store))
    assert c["EBS volume 1 (gp3, 100 GB) - storage"].monthly == "20.00"
    assert c["EBS volume 1 (gp3, 100 GB) - extra IOPS"].monthly == "10.00"  # 1000 x 0.005 x 2
    assert c["EBS volume 1 (gp3, 100 GB) - extra throughput"].monthly == "10.00"  # 125 x 0.04 x 2


def test_ebs_io1_iops(store):
    c = comps(calculate_item(ec2(ebs=[EbsVolume(volume_type="io1", size_gb=Decimal(50), iops=Decimal(1000))]), store))
    assert c["EBS volume 1 (io1, 50 GB) - provisioned IOPS"].monthly == "70.00"


def test_ebs_io2_iops_are_tiered(store):
    vol = EbsVolume(volume_type="io2", size_gb=Decimal(10), iops=Decimal(70000))
    c = comps(calculate_item(ec2(ebs=[vol]), store))
    # 32000 x 0.07 + 32000 x 0.05 + 6000 x 0.03 = 2240 + 1600 + 180
    assert c["EBS volume 1 (io2, 10 GB) - provisioned IOPS"].monthly == "4020.00"


def test_ebs_snapshot_formula_from_the_calculator(store):
    vol = EbsVolume(size_gb=Decimal(100), snapshots_per_month=4, snapshot_changed_gb=Decimal(10))
    c = comps(calculate_item(ec2(ebs=[vol]), store))
    # initial 100 x 0.05 = 5 ; each 10 x 0.05 = 0.5 ; halved 0.25 ; x4 = 1 ; total 6
    assert c["EBS volume 1 (gp3, 100 GB) - snapshots"].monthly == "6.00"


def test_ebs_billed_in_full_even_when_instance_mostly_off(store):
    vol = EbsVolume(size_gb=Decimal(100))
    res = calculate_item(ec2(usage=Usage(mode="percent_month", percent=Decimal(10)), ebs=[vol]), store)
    assert comps(res)["EBS volume 1 (gp3, 100 GB) - storage"].monthly == "10.00"
    assert any("whole month" in w for w in res.warnings)


# ------------------------------------------------------------------ S3 -----
def test_s3_tiered_storage(store):
    res = calculate_item(S3Item(region=R, storage_gb=Decimal(60000)), store)
    assert res.monthly == "1491.20"


def test_s3_requests_are_priced_per_request(store):
    res = calculate_item(S3Item(region=R, storage_gb=Decimal(0), put_requests=Decimal(1_000_000), get_requests=Decimal(5_000_000)), store)
    c = comps(res)
    assert c["S3 Standard - PUT, COPY, POST, LIST requests"].monthly == "5.00"  # 1e6 x 5e-6
    assert c["S3 Standard - GET, SELECT and other requests"].monthly == "2.00"  # 5e6 x 4e-7


def test_s3_ia_has_retrieval_fee(store):
    res = calculate_item(S3Item(region=R, storage_class="standard_ia", storage_gb=Decimal(1000), retrieval_gb=Decimal(200)), store)
    c = comps(res)
    assert c["S3 Standard-IA - storage"].monthly == "13.80"
    assert c["S3 Standard-IA - data retrieval"].monthly == "2.00"


def test_s3_standard_has_no_retrieval_fee(store):
    res = calculate_item(S3Item(region=R, storage_gb=Decimal(10), retrieval_gb=Decimal(5)), store)
    assert res.error and "retrieval" in res.error


def test_s3_class_without_prices_in_region_is_reported(store):
    res = calculate_item(S3Item(region=R, storage_class="glacier_ir", storage_gb=Decimal(10)), store)
    assert res.error


# ------------------------------------------------------------------ RDS ----
def rds(**kw):
    return RdsItem(region=R, instance_type="db.t3.medium", **kw)


def test_rds_single_az(store):
    res = calculate_item(rds(storage_gb=Decimal(100)), store)
    c = comps(res)
    assert c["RDS db.t3.medium PostgreSQL (Single-AZ)"].monthly == "73.00"
    assert c["RDS storage (gp3, Single-AZ)"].monthly == "13.00"


def test_rds_multi_az_uses_its_own_skus_not_a_doubling_rule(store):
    res = calculate_item(rds(deployment="multi_az", storage_gb=Decimal(100)), store)
    c = comps(res)
    assert c["RDS db.t3.medium PostgreSQL (Multi-AZ)"].monthly == "146.00"  # 0.20 SKU
    assert c["RDS storage (gp3, Multi-AZ)"].monthly == "26.00"  # 0.26 SKU


def test_rds_io1_provisioned_iops(store):
    res = calculate_item(rds(storage_type="io1", storage_gb=Decimal(100), iops=Decimal(1000)), store)
    assert comps(res)["RDS provisioned IOPS (io1)"].monthly == "100.00"


def test_rds_reserved_is_standard_class_only(store):
    p = Pricing(model="reserved", term="3yr", payment="partial_upfront")
    res = calculate_item(rds(pricing=p, storage_gb=Decimal(10)), store)
    assert res.upfront == "300.00"
    assert comps(res)["RDS db.t3.medium PostgreSQL (Single-AZ)"].monthly == "29.20"  # 730 x 0.04
    # monthly 29.20 + 1.30 storage = 30.50 ; effective = 30.50 + 300/36 months = 38.83
    assert res.effective_monthly == "38.83"


# --------------------------------------------------------- whole estimate --
def test_estimate_totals_are_sums_of_rounded_lines(store):
    sc = Scenario(name="t", items=[ec2(quantity=2), S3Item(region=R, storage_gb=Decimal(60000)), rds(storage_gb=Decimal(100))])
    est = calculate(sc, store)
    assert est.monthly == "1723.20"  # 146.00 + 1491.20 + (73.00 + 13.00)
    assert est.yearly == "20678.40"
    assert est.first_12_months == "20678.40" and est.upfront == "0.00"
    assert est.price_list_dates == {"ec2/ap-south-1": "2026-01-01", "s3/ap-south-1": "2026-01-01", "rds/ap-south-1": "2026-01-01"}


def test_failed_item_is_excluded_from_totals_but_listed(store):
    sc = Scenario(name="t", items=[ec2(), Ec2Item(region=R, instance_type="nope.large")])
    est = calculate(sc, store)
    assert est.monthly == "73.00"
    assert [i.error is None for i in est.items] == [True, False]


def test_empty_scenario_is_zero(store):
    est = calculate(Scenario(name="empty"), store)
    assert est.monthly == "0.00" and est.items == []


# ------------------------------------------------------- Savings Plans ----
def sp(plan="compute", term="1yr", payment="no_upfront", **kw):
    return ec2(pricing=Pricing(model="savings_plan", sp_type=plan, term=term, payment=payment), **kw)


def test_savings_plan_no_upfront(store):
    res = calculate_item(sp(quantity=2), store)
    assert (res.monthly, res.upfront, res.effective_monthly) == ("102.20", "0.00", "102.20")  # 2 x 730 x 0.07


def test_savings_plan_partial_upfront_is_half_paid_at_purchase(store):
    res = calculate_item(sp(payment="partial_upfront"), store)
    # effective 730 x 0.06 = 43.80/month; 50% up front = 43.80 x 12 x 0.5 = 262.80; 50% monthly = 21.90
    assert (res.monthly, res.upfront) == ("21.90", "262.80")
    assert res.effective_monthly == "43.80"  # same as paying 43.80 every month
    assert res.first_12_months == "525.60"


def test_savings_plan_all_upfront(store):
    res = calculate_item(sp(payment="all_upfront"), store)
    assert (res.monthly, res.upfront, res.effective_monthly) == ("0.00", "438.00", "36.50")  # 730 x 0.05 x 12


def test_savings_plan_three_year_term(store):
    res = calculate_item(sp(term="3yr"), store)
    assert res.monthly == "29.20"  # 730 x 0.04


def test_ec2_instance_plan_is_a_separate_price_from_compute_plan(store):
    assert calculate_item(sp(plan="ec2_instance"), store).monthly == "43.80"  # 0.06
    assert calculate_item(sp(plan="compute"), store).monthly == "51.10"  # 0.07


def test_savings_plan_ignores_utilization_like_reserved(store):
    res = calculate_item(sp(usage=Usage(mode="percent_month", percent=Decimal(10))), store)
    assert res.monthly == "51.10"


def test_unavailable_savings_plan_option_is_reported(store):
    res = calculate_item(sp(plan="ec2_instance", term="3yr"), store)
    assert res.error and "EC2 Instance Savings Plan" in res.error


def test_savings_plan_not_available_for_windows_here_is_reported_not_raised(store):
    res = calculate_item(sp(os="Windows"), store)
    assert res.error


def test_rds_rejects_savings_plans(store):
    p = Pricing(model="savings_plan", term="1yr")
    res = calculate_item(rds(pricing=p), store)
    assert res.error and "Reserved" in res.error


def test_savings_plan_vs_on_demand_compare_by_effective_monthly(store):
    est = calculate(Scenario(name="x", items=[sp(payment="all_upfront", quantity=2)]), store)
    assert est.upfront == "876.00" and est.effective_monthly == "73.00"


# -------------------------------------------------------- data transfer ----
def dt(**kw):
    return DataTransferItem(region=R, **kw)


def test_dt_first_100gb_to_internet_is_free(store):
    res = calculate_item(dt(internet_out_gb=Decimal(50)), store)
    assert res.monthly == "0.00"


def test_dt_free_tier_then_first_tier(store):
    # 10,340 GB - 100 free = 10,240 billable, all inside tier 1: 10240 x 0.10
    assert calculate_item(dt(internet_out_gb=Decimal(10340)), store).monthly == "1024.00"


def test_dt_spans_tiers_after_free_allowance(store):
    # 20,000 - 100 = 19,900 billable: 10,240 x 0.10 + 9,660 x 0.08 = 1024.00 + 772.80
    assert calculate_item(dt(internet_out_gb=Decimal(20000)), store).monthly == "1796.80"


def test_dt_without_free_tier(store):
    assert calculate_item(dt(internet_out_gb=Decimal(150), apply_free_tier=False), store).monthly == "15.00"


def test_dt_inter_region(store):
    res = calculate_item(dt(inter_region_gb=Decimal(1000), destination_region="us-east-1"), store)
    assert res.monthly == "80.00"


def test_dt_inter_region_needs_a_valid_destination(store):
    assert calculate_item(dt(inter_region_gb=Decimal(10)), store).error
    assert calculate_item(dt(inter_region_gb=Decimal(10), destination_region="mars-1"), store).error
    # Wavelength zones are not ingested as destinations
    assert calculate_item(dt(inter_region_gb=Decimal(10), destination_region="us-west-2-wl1-den1"), store).error


def test_dt_cross_az_is_billed_in_both_directions(store):
    res = calculate_item(dt(cross_az_gb=Decimal(500)), store)
    assert res.monthly == "10.00"  # 500 x 0.01 x 2


def test_dt_components_add_up(store):
    res = calculate_item(dt(internet_out_gb=Decimal(150), apply_free_tier=False, cross_az_gb=Decimal(500),
                            inter_region_gb=Decimal(100), destination_region="us-east-1"), store)
    assert [c.monthly for c in res.components] == ["15.00", "8.00", "10.00"]
    assert res.monthly == "33.00"
