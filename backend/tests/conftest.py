from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.pricing.ingest import ingest_file, ingest_savings_plans
from app.pricing.store import PriceStore, connect, init_schema

from .fixtures import write_offers

REGION = "ap-south-1"


@pytest.fixture(scope="session")
def price_db(tmp_path_factory):
    root = tmp_path_factory.mktemp("offers")
    paths = write_offers(root, REGION)
    db = root / "prices.db"
    conn = connect(db)
    init_schema(conn)
    for service in ("ec2", "s3", "rds", "dt"):
        ingest_file(conn, service, REGION, paths[service])
    ingest_savings_plans(conn, REGION, paths["sp"])  # must come after ec2
    conn.close()
    return db


@pytest.fixture()
def store(price_db):
    return PriceStore(connect(price_db))


@pytest.fixture()
def client(price_db):
    return TestClient(create_app(price_db=price_db, scenario_db=":memory:"))
