import json

import pytest

from app.pricing.ingest import ingest_file
from app.pricing.store import connect, init_schema

from .fixtures import ec2_offer


def test_gate_rejects_file_where_normalizers_match_nothing(tmp_path):
    """Simulates AWS renaming product families: nothing matches -> ingest must fail loudly."""
    offer = ec2_offer()
    for p in offer["products"].values():
        p["productFamily"] = "Renamed Family"
    path = tmp_path / "ec2.json"
    path.write_text(json.dumps(offer))
    conn = connect(tmp_path / "db.sqlite")
    init_schema(conn)
    with pytest.raises(RuntimeError, match="Data-quality gate"):
        ingest_file(conn, "ec2", "ap-south-1", path)
    assert conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0] == 0


def test_gate_rejects_negative_prices(tmp_path):
    offer = ec2_offer()
    offer["terms"]["OnDemand"]["EC2LINUX"]["EC2LINUX.OD"]["priceDimensions"]["EC2LINUX.OD.1"]["pricePerUnit"]["USD"] = "-1"
    path = tmp_path / "ec2.json"
    path.write_text(json.dumps(offer))
    conn = connect(tmp_path / "db.sqlite")
    init_schema(conn)
    with pytest.raises(RuntimeError, match="negative"):
        ingest_file(conn, "ec2", "ap-south-1", path)
