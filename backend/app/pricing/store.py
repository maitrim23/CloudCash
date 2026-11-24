"""Read side of the price database."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ..engine.tiers import Tier

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


@dataclass(frozen=True)
class Rate:
    unit: str
    begin: Decimal
    end: Decimal | None
    price: Decimal
    term: str
    lease: str
    offering: str
    payment: str
    sku: str
    rate_code: str


class PriceNotFound(LookupError):
    """Raised when the price file has no matching price (unsupported combination)."""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


class PriceStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- metadata -----------------------------------------------------------
    def meta(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT service, region, version, publication_date, ingested_at, product_count, rate_count "
            "FROM meta ORDER BY service, region"
        ).fetchall()
        return [dict(r) for r in rows]

    def regions(self, service: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT region FROM meta WHERE service = ? ORDER BY region", (service,)
        ).fetchall()
        return [r["region"] for r in rows]

    def publication_date(self, service: str, region: str) -> str | None:
        row = self.conn.execute(
            "SELECT publication_date FROM meta WHERE service = ? AND region = ?", (service, region)
        ).fetchone()
        return row["publication_date"] if row else None

    # -- catalog ------------------------------------------------------------
    def products(self, service: str, region: str, family: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT key, attrs FROM product WHERE service = ? AND region = ? AND family = ? ORDER BY key",
            (service, region, family),
        ).fetchall()
        return [{"key": r["key"], **json.loads(r["attrs"])} for r in rows]

    def product(self, service: str, region: str, family: str, key: str) -> dict:
        row = self.conn.execute(
            "SELECT attrs FROM product WHERE service = ? AND region = ? AND family = ? AND key = ?",
            (service, region, family, key),
        ).fetchone()
        if not row:
            raise PriceNotFound(f"{service}/{family}: '{key}' is not available in {region}")
        return json.loads(row["attrs"])

    # -- prices -------------------------------------------------------------
    def rates(
        self,
        service: str,
        region: str,
        family: str,
        key: str,
        term: str = "OnDemand",
        lease: str = "",
        offering: str = "",
        payment: str = "",
    ) -> list[Rate]:
        rows = self.conn.execute(
            'SELECT unit, begin, "end", price, term, lease, offering, payment, sku, rate_code FROM rate '
            "WHERE service = ? AND region = ? AND family = ? AND key = ? AND term = ? "
            "AND lease = ? AND offering = ? AND payment = ?",
            (service, region, family, key, term, lease, offering, payment),
        ).fetchall()
        result = [
            Rate(
                unit=r["unit"],
                begin=Decimal(r["begin"]),
                end=None if r["end"] is None else Decimal(r["end"]),
                price=Decimal(r["price"]),
                term=r["term"],
                lease=r["lease"],
                offering=r["offering"],
                payment=r["payment"],
                sku=r["sku"],
                rate_code=r["rate_code"],
            )
            for r in rows
        ]
        result.sort(key=lambda r: (r.unit, r.begin))
        return result

    def require_rates(self, *args, **kwargs) -> list[Rate]:
        rates = self.rates(*args, **kwargs)
        if not rates:
            parts = ", ".join(f"{k}={v}" for k, v in {**dict(zip(("service", "region", "family", "key"), args)), **kwargs}.items())
            raise PriceNotFound(f"No price found for {parts}")
        return rates

    def single_price(self, service: str, region: str, family: str, key: str, unit: str | None = None, **kw) -> Rate:
        """Exactly-one-price lookup (hourly fee, flat GB-month price ...)."""
        rates = self.require_rates(service, region, family, key, **kw)
        if unit is not None:
            rates = [r for r in rates if r.unit == unit]
            if not rates:
                raise PriceNotFound(f"No '{unit}' price for {service}/{family}/{key} in {region}")
        return rates[0]

    def tiers(self, service: str, region: str, family: str, key: str, unit: str | None = None, **kw) -> list[Tier]:
        rates = self.require_rates(service, region, family, key, **kw)
        if unit is not None:
            rates = [r for r in rates if r.unit == unit]
        return [Tier(start=r.begin, end=r.end, price=r.price) for r in sorted(rates, key=lambda r: r.begin)]
