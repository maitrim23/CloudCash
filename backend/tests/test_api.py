R = "ap-south-1"

EC2 = {"type": "ec2", "name": "web", "region": R, "instance_type": "m5.large", "quantity": 2}
RI = {**EC2, "name": "web-ri", "pricing": {"model": "reserved", "term": "1yr", "payment": "all_upfront"}}


def scenario(name="s", *items):
    return {"name": name, "items": list(items) or [EC2]}


def test_health(client):
    assert client.get("/api/health").json() == {"status": "healthy"}


def test_meta_lists_regions_and_price_dates(client):
    body = client.get("/api/meta").json()
    assert body["regions"] == [{"region": R, "price_list_dates": {"dt": "2026-01-01", "ec2": "2026-01-01", "ec2sp": "2026-01-01", "rds": "2026-01-01", "s3": "2026-01-01"}}]


def test_catalogs(client):
    ec2 = client.get("/api/catalog/ec2", params={"region": R}).json()
    assert [i["instance_type"] for i in ec2["instances"]] == ["m1.large", "m5.large", "m6i.xlarge", "t3.small", "t3a.large"]
    m5 = next(i for i in ec2["instances"] if i["instance_type"] == "m5.large")
    assert sorted(m5["os"]) == ["Linux", "Windows"]
    rds = client.get("/api/catalog/rds", params={"region": R}).json()
    assert [e["engine"] for e in rds["engines"]] == ["PostgreSQL"]  # Aurora hidden
    assert client.get("/api/catalog/s3").json()["storage_classes"][0] == {"id": "standard", "label": "S3 Standard"}


def test_catalog_unknown_region_is_404(client):
    assert client.get("/api/catalog/ec2", params={"region": "mars-1"}).status_code == 404


def test_estimate(client):
    r = client.post("/api/estimate", json=scenario("e"))
    assert r.status_code == 200
    body = r.json()
    assert body["monthly"] == "146.00" and body["yearly"] == "1752.00"
    assert body["items"][0]["components"][0]["explain"]


def test_estimate_validation_errors_are_422(client):
    bad = {"name": "x", "items": [{**EC2, "quantity": 0}]}
    assert client.post("/api/estimate", json=bad).status_code == 422
    unknown_type = {"name": "x", "items": [{"type": "lambda", "region": R}]}
    assert client.post("/api/estimate", json=unknown_type).status_code == 422


def test_estimate_survives_one_bad_line(client):
    sc = scenario("mix", EC2, {**EC2, "instance_type": "nope.large"})
    body = client.post("/api/estimate", json=sc).json()
    assert body["monthly"] == "146.00"
    assert body["items"][1]["error"]


def test_compare_ranks_by_effective_monthly(client):
    r = client.post("/api/compare", json={"scenarios": [scenario("on-demand", EC2), scenario("reserved", RI)]})
    assert r.status_code == 200
    body = r.json()
    assert body["baseline"] == "on-demand" and body["cheapest"] == "reserved"
    od, ri = body["diffs"]
    assert od["vs_baseline"] == "0.00"
    # all-upfront: 2 x 500 / 12 = 83.33 vs on-demand 146.00
    assert ri["effective_monthly"] == "83.33" and ri["vs_baseline"] == "-62.67" and ri["vs_baseline_pct"] == "-42.92"


def test_compare_needs_two_to_four_scenarios(client):
    assert client.post("/api/compare", json={"scenarios": [scenario()]}).status_code == 422
    assert client.post("/api/compare", json={"scenarios": [scenario()] * 5}).status_code == 422


def test_saved_scenarios_crud(client):
    created = client.post("/api/scenarios", json=scenario("mine"))
    assert created.status_code == 201
    sid = created.json()["id"]
    assert [s["name"] for s in client.get("/api/scenarios").json()] == ["mine"]
    assert client.get(f"/api/scenarios/{sid}").json()["scenario"]["items"][0]["instance_type"] == "m5.large"

    updated = client.put(f"/api/scenarios/{sid}", json=scenario("renamed"))
    assert updated.json()["name"] == "renamed"

    assert client.delete(f"/api/scenarios/{sid}").status_code == 204
    assert client.get(f"/api/scenarios/{sid}").status_code == 404
    assert client.delete(f"/api/scenarios/{sid}").status_code == 404


def test_scenarios_are_private_per_session(price_db):
    from fastapi.testclient import TestClient
    from app.main import create_app

    app = create_app(price_db=price_db, scenario_db=":memory:")
    alice, bob = TestClient(app), TestClient(app)
    sid = alice.post("/api/scenarios", json=scenario("alice's")).json()["id"]
    assert bob.get("/api/scenarios").json() == []
    assert bob.get(f"/api/scenarios/{sid}").status_code == 404
    assert bob.delete(f"/api/scenarios/{sid}").status_code == 404
    assert len(alice.get("/api/scenarios").json()) == 1


def test_data_transfer_catalog_and_estimate(client):
    cat = client.get("/api/catalog/dt", params={"region": R}).json()
    assert cat["destinations"] == [{"region": "us-east-1", "name": "US East (N. Virginia)"}]
    body = {"name": "dt", "items": [{"type": "dt", "region": R, "inter_region_gb": 100, "destination_region": "us-east-1"}]}
    assert client.post("/api/estimate", json=body).json()["monthly"] == "8.00"
    assert client.get("/api/catalog/dt", params={"region": "mars-1"}).status_code == 404


def test_rightsizing_suggests_cheaper_with_at_least_same_specs(client):
    body = client.get("/api/ec2/alternatives", params={"region": R, "instance_type": "m5.large"}).json()
    # t3a.large: same 2 vCPU / 8 GiB, $0.08 vs $0.10 -> 20% cheaper.
    # NOT suggested: m6i.xlarge (dearer), t3.small (too small), m1.large (previous generation).
    assert body["alternatives"] == [{"instance_type": "t3a.large", "vcpu": 2, "memory_gib": "8", "hourly": "0.0800000000", "saving_pct": "20.0", "arm": False}]


def test_rightsizing_unknown_instance_is_404(client):
    assert client.get("/api/ec2/alternatives", params={"region": R, "instance_type": "zz.large"}).status_code == 404


def test_serves_built_frontend_without_shadowing_the_api(price_db, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    (tmp_path / "index.html").write_text("<html><title>CostGoblin</title></html>")
    (tmp_path / "app.js").write_text("console.log(1)")
    c = TestClient(create_app(price_db=price_db, scenario_db=":memory:", static_dir=tmp_path))
    assert "CostGoblin" in c.get("/").text
    assert c.get("/app.js").text == "console.log(1)"
    assert c.get("/api/health").json() == {"status": "healthy"}  # API routes still win
    assert c.get("/api/nope").status_code == 404


def test_secure_cookie_flag_is_opt_in(price_db, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app

    monkeypatch.setenv("COOKIE_SECURE", "1")
    c = TestClient(create_app(price_db=price_db, scenario_db=":memory:", static_dir="/nonexistent"))
    header = c.get("/api/scenarios").headers["set-cookie"]
    assert "Secure" in header and "HttpOnly" in header and "SameSite=lax" in header
