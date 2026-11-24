"""Cheaper-alternative suggestions, computed from the price data.

An alternative must have at least the same vCPU and memory as the instance the user
picked, be a current-generation type, and cost less per hour On-Demand in the same
region and OS. This is a *hint*: it knows nothing about CPU architecture (x86 vs
Arm/Graviton), network, instance store or your software, so the UI says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from ..pricing.store import PriceNotFound, PriceStore
from .money import round_money

_MEM = re.compile(r"([\d.,]+)")


def parse_memory_gib(text: str | None) -> Decimal | None:
    """'8 GiB' -> 8, '1,024 GiB' -> 1024. None if unparseable."""
    if not text:
        return None
    m = _MEM.search(text)
    return Decimal(m.group(1).replace(",", "")) if m else None


@dataclass(frozen=True)
class Alternative:
    instance_type: str
    vcpu: int
    memory_gib: Decimal
    hourly: Decimal
    saving_pct: Decimal  # vs the chosen instance, positive = cheaper
    arm: bool = False  # AWS Graviton (Arm): needs Arm-compatible software, not a drop-in swap


def find_alternatives(store: PriceStore, region: str, instance_type: str, os: str, limit: int = 5) -> tuple[Decimal, list[Alternative]]:
    key = f"{instance_type}|{os}"
    base_spec = store.product("ec2", region, "ec2_instance", key)
    base_price = store.single_price("ec2", region, "ec2_instance", key, unit="Hrs", term="OnDemand").price
    base_vcpu = int(base_spec["vcpu"])
    base_mem = parse_memory_gib(base_spec.get("memory"))
    if base_mem is None:
        raise PriceNotFound(f"Cannot read the memory size of {instance_type}")

    rows = store.conn.execute(
        "SELECT p.key, p.attrs, r.price FROM product p JOIN rate r "
        "ON r.service=p.service AND r.region=p.region AND r.family=p.family AND r.key=p.key "
        "WHERE p.service='ec2' AND p.region=? AND p.family='ec2_instance' AND p.key LIKE ? "
        "AND r.term='OnDemand' AND r.unit='Hrs'",
        (region, f"%|{os}"),
    ).fetchall()

    import json

    found: list[Alternative] = []
    for row in rows:
        attrs = json.loads(row["attrs"])
        itype = attrs["instanceType"]
        if itype == instance_type or attrs.get("currentGeneration") != "Yes":
            continue
        try:
            vcpu, mem, price = int(attrs["vcpu"]), parse_memory_gib(attrs.get("memory")), Decimal(row["price"])
        except (KeyError, ValueError):
            continue
        if mem is None or vcpu < base_vcpu or mem < base_mem or price >= base_price or price <= 0:
            continue
        saving = (base_price - price) / base_price * 100
        arm = "graviton" in (attrs.get("physicalProcessor") or "").lower()
        found.append(Alternative(itype, vcpu, mem, price, round_money(saving, 1), arm))
    found.sort(key=lambda a: (a.hourly, a.instance_type))
    return base_price, found[:limit]
