from decimal import Decimal

from app.pricing.ingest import normalize_ec2, normalize_rds, normalize_s3, strip_region_prefix

R = "ap-south-1"


def test_strip_region_prefix():
    assert strip_region_prefix("APS3-Requests-Tier1") == "Requests-Tier1"
    assert strip_region_prefix("EUW1-Retrieval-SIA") == "Retrieval-SIA"
    assert strip_region_prefix("Requests-Tier1") == "Requests-Tier1"  # us-east-1 has no prefix


def test_ec2_keeps_only_shared_used_unlicensed_instances(store):
    keys = {p["key"] for p in store.products("ec2", R, "ec2_instance")}
    # The Dedicated-tenancy SKU (EC2DED, $9/h) is absent: only Shared/Used/NA-software rows are kept.
    assert keys == {
        "m5.large|Linux", "m5.large|Windows",
        "t3a.large|Linux", "m6i.xlarge|Linux", "t3.small|Linux", "m1.large|Linux",
    }


def test_ec2_filters_outposts_snapshots(store):
    assert store.single_price("ec2", R, "ebs_snapshot", "standard").price == Decimal("0.05")


def test_io2_tiers_get_separate_keys(store):
    prices = [store.single_price("ec2", R, "ebs_iops", f"io2:tier{n}").price for n in (1, 2, 3)]
    assert prices == [Decimal("0.07"), Decimal("0.05"), Decimal("0.03")]


def test_s3_tags_are_not_ingested(store):
    keys = {p["key"] for p in store.products("s3", R, "s3_storage")}
    assert keys == {"Standard", "Standard - Infrequent Access"}


def test_s3_tier_ranges_are_ingested_in_order(store):
    tiers = store.tiers("s3", R, "s3_storage", "Standard")
    assert [(t.start, t.end) for t in tiers] == [(Decimal(0), Decimal(51200)), (Decimal(51200), Decimal(512000)), (Decimal(512000), None)]


def test_rds_ignores_readable_standby_deployments(store):
    keys = {p["key"] for p in store.products("rds", R, "rds_instance")}
    assert all(k.endswith(("Single-AZ", "Multi-AZ")) and "standbys" not in k for k in keys)


def test_rds_iops_kinds_are_distinguished_by_usagetype(store):
    for kind, price in (("io1", "0.1"), ("io2", "0.09"), ("gp3", "0.02")):
        assert store.single_price("rds", R, "rds_iops", f"{kind}|Single-AZ|PostgreSQL").price == Decimal(price)


def test_reserved_rates_only_for_instance_families(store):
    assert store.rates("ec2", R, "ec2_instance", "m5.large|Linux", term="Reserved", lease="1yr", offering="standard", payment="Partial Upfront")
    assert store.rates("ec2", R, "ebs_storage", "gp3", term="Reserved") == []


def test_meta_records_price_list_version(store):
    assert store.publication_date("ec2", R) == "2026-01-01T00:00:00Z"
    assert {m["service"] for m in store.meta()} == {"ec2", "ec2sp", "s3", "rds", "dt"}


def test_normalizers_ignore_unknown_families():
    assert normalize_ec2({"productFamily": "Data Transfer", "attributes": {}}) is None
    assert normalize_s3({"productFamily": "Fee", "attributes": {}}) is None
    assert normalize_rds({"productFamily": "RDSProxy", "attributes": {}}) is None


def test_savings_plans_are_joined_on_sku_and_only_hourly_rates_kept(store):
    rows = store.rates("ec2", R, "ec2_instance", "m5.large|Linux", term="SavingsPlan", lease="1yr", offering="compute", payment="No Upfront")
    assert [(r.unit, r.price) for r in rows] == [("Hrs", Decimal("0.07"))]


def test_savings_plan_meta_is_recorded(store):
    assert store.publication_date("ec2sp", R) == "2026-01-01T00:00:00Z"


def test_savings_plans_require_ec2_first(tmp_path):
    import pytest
    from app.pricing.ingest import ingest_savings_plans
    from app.pricing.store import connect, init_schema
    from .fixtures import write_offers
    paths = write_offers(tmp_path)
    conn = connect(tmp_path / "x.db")
    init_schema(conn)
    with pytest.raises(RuntimeError, match="ingest 'ec2' before 'sp'"):
        ingest_savings_plans(conn, R, paths["sp"])


def test_reingesting_ec2_invalidates_savings_plans(tmp_path):
    from app.pricing.ingest import ingest_file, ingest_savings_plans
    from app.pricing.store import PriceStore, connect, init_schema
    from .fixtures import write_offers
    paths = write_offers(tmp_path)
    conn = connect(tmp_path / "y.db")
    init_schema(conn)
    ingest_file(conn, "ec2", R, paths["ec2"])
    ingest_savings_plans(conn, R, paths["sp"])
    ingest_file(conn, "ec2", R, paths["ec2"])  # EC2 re-run wipes SP rows...
    assert PriceStore(conn).publication_date("ec2sp", R) is None  # ...so the stale marker goes too


def test_data_transfer_ingest_shapes(store):
    tiers = store.tiers("dt", R, "dt_internet_out", "internet")
    assert [(t.start, t.end, t.price) for t in tiers][0] == (Decimal(0), Decimal(10240), Decimal("0.1"))
    assert store.single_price("dt", R, "dt_free", "internet_out").end == Decimal(100)
    assert {p["key"] for p in store.products("dt", R, "dt_interregion")} == {"us-east-1"}  # wavelength dropped
    assert store.products("dt", R, "dt_cross_az")


# ------------------------------------------------------------ downloads ----
def test_download_retries_and_never_leaves_a_partial_file(tmp_path, monkeypatch):
    import io
    from app.pricing import ingest

    monkeypatch.setattr(ingest, "OFFER_DIR", tmp_path)
    calls = {"n": 0}

    class Flaky(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        assert timeout, "every download must have a timeout, otherwise a stalled connection hangs forever"
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("stalled")
        return Flaky(b'{"ok": true}')

    monkeypatch.setattr(ingest.urllib.request, "urlopen", fake_urlopen)
    path = ingest.download("s3", "ap-south-1")
    assert path.read_bytes() == b'{"ok": true}' and calls["n"] == 2
    assert not list(tmp_path.rglob("*.part"))


def test_download_gives_up_after_three_attempts_and_cleans_up(tmp_path, monkeypatch):
    import pytest
    from app.pricing import ingest

    monkeypatch.setattr(ingest, "OFFER_DIR", tmp_path)

    def always_fails(req, timeout=None):
        raise TimeoutError("stalled")

    monkeypatch.setattr(ingest.urllib.request, "urlopen", always_fails)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        ingest.download("s3", "ap-south-1")
    assert not list(tmp_path.rglob("*"))  or all(p.is_dir() for p in tmp_path.rglob("*"))  # no file, no .part
