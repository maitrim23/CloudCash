"""Golden cases taken from AWS's own published pricing examples.

Source: https://aws.amazon.com/ebs/pricing/  ("Pricing examples", fetched 2026-11-24) and the
S3 pricing page's replication example. AWS states the unit rates inside each example, so we load
exactly those rates into a throw-away price database and check that OUR formulas reproduce AWS's
printed totals. This validates the maths independent of today's prices.

AWS's EBS examples bill a volume for 12 hours of a 30-day month: 43,200 / (86,400 x 30) = 1/60.
CostGoblin bills EBS storage for the whole month, so every AWS figure is compared as `ours / 60`.
"""

from decimal import Decimal

import pytest

from app.engine.estimate import calculate_item
from app.pricing.store import PriceStore, connect, init_schema
from app.schemas import DataTransferItem, EbsVolume, Ec2Item

R = "test-region-1"
D = Decimal
FRACTION = D(60)  # a full month is 60x AWS's 12-hour example


@pytest.fixture()
def aws_example_store(tmp_path):
    conn = connect(tmp_path / "golden.db")
    init_schema(conn)

    def put(service, family, key, unit, price, begin="0", end=None):
        conn.execute(
            'INSERT INTO rate (service, region, family, key, term, unit, begin, "end", price, sku, rate_code) '
            "VALUES (?,?,?,?, 'OnDemand', ?,?,?,?, 'S', 'R')", (service, R, family, key, unit, begin, end, price))

    def product(service, family, key, **attrs):
        import json
        conn.execute("INSERT INTO product (service, region, family, key, attrs) VALUES (?,?,?,?,?)", (service, R, family, key, json.dumps(attrs)))

    # an instance priced at $0 so only the EBS lines matter
    product("ec2", "ec2_instance", "m5.large|Linux", instanceType="m5.large", vcpu="2", memory="8 GiB")
    put("ec2", "ec2_instance", "m5.large|Linux", "Hrs", "0")

    # rates exactly as printed in AWS's examples
    put("ec2", "ebs_storage", "gp3", "GB-Mo", "0.08")
    put("ec2", "ebs_iops", "gp3", "IOPS-Mo", "0.005")
    put("ec2", "ebs_throughput", "gp3", "GiBps-mo", str(D("0.06") * 1024))  # AWS: $0.06 per MB/s-month
    put("ec2", "ebs_storage", "gp2", "GB-Mo", "0.10")
    put("ec2", "ebs_storage", "io1", "GB-Mo", "0.125")
    put("ec2", "ebs_iops", "io1", "IOPS-Mo", "0.065")
    put("ec2", "ebs_storage", "io2", "GB-month", "0.125")
    put("ec2", "ebs_iops", "io2:tier1", "IOPS-Mo", "0.065")
    put("ec2", "ebs_iops", "io2:tier2", "IOPS-Mo", "0.046")
    put("ec2", "ebs_iops", "io2:tier3", "IOPS-Mo", "0.032")  # AWS gives no figure for tier 3; unused below
    put("ec2", "ebs_storage", "st1", "GB-Mo", "0.045")
    put("ec2", "ebs_storage", "sc1", "GB-Mo", "0.015")

    # inter-region transfer example: $0.02/GB out of Oregon
    product("dt", "dt_interregion", "us-east-1", to_region="us-east-1", to_name="US East (N. Virginia)")
    put("dt", "dt_interregion", "us-east-1", "GB", "0.02")
    conn.commit()
    return PriceStore(conn)


def ebs_components(store, **vol):
    item = Ec2Item(region=R, instance_type="m5.large", ebs=[EbsVolume(**vol)])
    res = calculate_item(item, store)
    assert res.error is None, res.error
    return {c.label.split(" - ")[-1]: D(c.monthly) for c in res.components if c.label.startswith("EBS")}


def assert_matches_aws(ours_full_month: Decimal, aws_12h: str, tolerance="0.002"):
    """AWS prints 12-hour figures to 3 decimals; allow for that rounding."""
    assert abs(ours_full_month / FRACTION - D(aws_12h)) <= D(tolerance), f"{ours_full_month}/60 != {aws_12h}"


def test_aws_example1_gp3_with_extra_iops_and_throughput(aws_example_store):
    # 2,000 GB, 10,000 IOPS, 500 MB/s.  AWS: storage $2.667, IOPS $0.583, throughput $0.375, total $3.625
    c = ebs_components(aws_example_store, volume_type="gp3", size_gb=D(2000), iops=D(10000), throughput_mbps=D(500))
    assert_matches_aws(c["storage"], "2.667")
    assert_matches_aws(c["extra IOPS"], "0.583")  # (10,000 - 3,000 free) x $0.005
    assert_matches_aws(c["extra throughput"], "0.375")  # (500 - 125 free) x $0.06
    assert_matches_aws(sum(c.values()), "3.625")


def test_aws_example2_gp2(aws_example_store):
    c = ebs_components(aws_example_store, volume_type="gp2", size_gb=D(2000))
    assert_matches_aws(c["storage"], "3.33", tolerance="0.005")  # AWS prints 2 d.p.: $3.33 (true value 3.3333)


def test_aws_example3_io2_small_volume(aws_example_store):
    c = ebs_components(aws_example_store, volume_type="io2", size_gb=D(2000), iops=D(1000))
    assert_matches_aws(c["storage"], "4.167")
    assert_matches_aws(c["provisioned IOPS"], "1.083")


def test_aws_example3_io2_iops_are_graduated_across_tiers(aws_example_store):
    # 60,000 IOPS: (0.065 x 32,000 + 0.046 x 28,000) = 3,368 per month; AWS prints $56.133 for 12 h
    c = ebs_components(aws_example_store, volume_type="io2", size_gb=D(2000), iops=D(60000))
    assert c["provisioned IOPS"] == D("3368.00")
    assert_matches_aws(c["provisioned IOPS"], "56.133")


def test_aws_example4_io1(aws_example_store):
    c = ebs_components(aws_example_store, volume_type="io1", size_gb=D(2000), iops=D(1000))
    assert_matches_aws(c["storage"], "4.167")
    assert_matches_aws(c["provisioned IOPS"], "1.083")
    assert_matches_aws(sum(c.values()), "5.25")  # AWS total


def test_aws_example5_and_6_hdd_volumes(aws_example_store):
    assert_matches_aws(ebs_components(aws_example_store, volume_type="st1", size_gb=D(2000))["storage"], "1.50")
    assert_matches_aws(ebs_components(aws_example_store, volume_type="sc1", size_gb=D(2000))["storage"], "0.50")


def test_aws_s3_replication_example_inter_region_transfer(aws_example_store):
    # AWS (S3 Tables replication example): 147.66 GB out of Oregon at $0.02/GB = $2.95
    item = DataTransferItem(region=R, inter_region_gb=D("147.66"), destination_region="us-east-1")
    assert calculate_item(item, aws_example_store).monthly == "2.95"
