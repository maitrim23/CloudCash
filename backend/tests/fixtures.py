"""Tiny synthetic AWS offer files with round prices, so expected values are
hand-computable. They have the real file structure, so the real ingest code
(normalizers, streaming, tier keys) is exercised too."""

from __future__ import annotations

import json
from pathlib import Path


def _dim(sku, term, unit, price, begin="0", end="Inf", n=1):
    code = f"{sku}.{term}.{n}"
    return {
        code: {"rateCode": code, "unit": unit, "beginRange": begin, "endRange": end,
               "pricePerUnit": {"USD": price}, "description": "x", "appliesTo": []}
    }


def _term(sku, term_code, dims, attrs=None):
    return {f"{sku}.{term_code}": {"offerTermCode": term_code, "sku": sku, "priceDimensions": dims, "termAttributes": attrs or {}}}


def build_offer(offer_code: str, products: list[tuple[str, dict]], on_demand: dict, reserved: dict | None = None) -> dict:
    return {
        "formatVersion": "v1.0", "offerCode": offer_code, "version": "20260101000000",
        "publicationDate": "2026-01-01T00:00:00Z",
        "products": {sku: {"sku": sku, **p} for sku, p in products},
        "terms": {"OnDemand": on_demand, "Reserved": reserved or {}},
    }


def ec2_offer() -> dict:
    inst = {"servicecode": "AmazonEC2", "instanceType": "m5.large", "instanceFamily": "General purpose", "vcpu": "2",
            "memory": "8 GiB", "storage": "EBS only", "networkPerformance": "Up to 10 Gigabit",
            "tenancy": "Shared", "capacitystatus": "Used", "preInstalledSw": "NA", "licenseModel": "No License required",
            "operatingSystem": "Linux", "regionCode": "ap-south-1", "location": "Asia Pacific (Mumbai)", "currentGeneration": "Yes"}
    win = {**inst, "operatingSystem": "Windows"}
    cheaper = {**inst, "instanceType": "t3a.large", "memory": "8 GiB"}           # same specs, cheaper
    bigger_cheaper = {**inst, "instanceType": "m6i.xlarge", "vcpu": "4", "memory": "16 GiB"}  # more, but dearer
    smaller = {**inst, "instanceType": "t3.small", "vcpu": "1", "memory": "2 GiB"}  # cheaper but too small
    old_gen = {**inst, "instanceType": "m1.large", "currentGeneration": "No"}       # cheaper but previous gen
    dedicated = {**inst, "tenancy": "Dedicated"}  # must be filtered out
    products = [
        ("EC2LINUX", {"productFamily": "Compute Instance", "attributes": inst}),
        ("EC2WIN", {"productFamily": "Compute Instance", "attributes": win}),
        ("EC2DED", {"productFamily": "Compute Instance", "attributes": dedicated}),
        ("EC2CHEAP", {"productFamily": "Compute Instance", "attributes": cheaper}),
        ("EC2BIG", {"productFamily": "Compute Instance", "attributes": bigger_cheaper}),
        ("EC2SMALL", {"productFamily": "Compute Instance", "attributes": smaller}),
        ("EC2OLD", {"productFamily": "Compute Instance", "attributes": old_gen}),
        ("GP3", {"productFamily": "Storage", "attributes": {"volumeApiName": "gp3", "volumeType": "General Purpose"}}),
        ("IO1", {"productFamily": "Storage", "attributes": {"volumeApiName": "io1", "volumeType": "Provisioned IOPS"}}),
        ("IO2", {"productFamily": "Storage", "attributes": {"volumeApiName": "io2", "volumeType": "Provisioned IOPS"}}),
        ("GP3IOPS", {"productFamily": "System Operation", "attributes": {"volumeApiName": "gp3", "group": "EBS IOPS", "usagetype": "APS3-EBS:VolumeP-IOPS.gp3"}}),
        ("IO1IOPS", {"productFamily": "System Operation", "attributes": {"volumeApiName": "io1", "group": "EBS IOPS", "usagetype": "APS3-EBS:VolumeP-IOPS.piops"}}),
        ("IO2T1", {"productFamily": "System Operation", "attributes": {"volumeApiName": "io2", "group": "EBS IOPS", "usagetype": "APS3-EBS:VolumeP-IOPS.io2"}}),
        ("IO2T2", {"productFamily": "System Operation", "attributes": {"volumeApiName": "io2", "group": "EBS IOPS Tier 2", "usagetype": "APS3-EBS:VolumeP-IOPS.io2.tier2"}}),
        ("IO2T3", {"productFamily": "System Operation", "attributes": {"volumeApiName": "io2", "group": "EBS IOPS Tier 3", "usagetype": "APS3-EBS:VolumeP-IOPS.io2.tier3"}}),
        ("GP3TP", {"productFamily": "Provisioned Throughput", "attributes": {"volumeApiName": "gp3"}}),
        ("SNAP", {"productFamily": "Storage Snapshot", "attributes": {"usagetype": "APS3-EBS:SnapshotUsage"}}),
        ("SNAPX", {"productFamily": "Storage Snapshot", "attributes": {"usagetype": "APS3-EBS:SnapshotUsage.outposts"}}),
    ]
    od = {}
    for sku, unit, price in [
        ("EC2LINUX", "Hrs", "0.1000000000"), ("EC2WIN", "Hrs", "0.2000000000"), ("EC2DED", "Hrs", "9.0"),
        ("EC2CHEAP", "Hrs", "0.0800000000"), ("EC2BIG", "Hrs", "0.2000000000"), ("EC2SMALL", "Hrs", "0.0200000000"), ("EC2OLD", "Hrs", "0.0500000000"),
        ("GP3", "GB-Mo", "0.1000000000"), ("IO1", "GB-Mo", "0.1500000000"), ("IO2", "GB-month", "0.1500000000"),
        ("GP3IOPS", "IOPS-Mo", "0.0050000000"), ("IO1IOPS", "IOPS-Mo", "0.0700000000"),
        ("IO2T1", "IOPS-Mo", "0.0700000000"), ("IO2T2", "IOPS-Mo", "0.0500000000"), ("IO2T3", "IOPS-Mo", "0.0300000000"),
        ("GP3TP", "GiBps-mo", "40.9600000000"),  # 40.96 / 1024 = 0.04 per MB/s
        ("SNAP", "GB-Mo", "0.0500000000"), ("SNAPX", "GB-Mo", "7.0"),
    ]:
        od.update(_term(sku, "OD", _dim(sku, "OD", unit, price)))
    reserved = {}
    for pay, hourly, upfront in (("No Upfront", "0.0600000000", None), ("Partial Upfront", "0.0300000000", "260"), ("All Upfront", "0.0000000000", "500")):
        dims = _dim("EC2LINUX", pay, "Hrs", hourly, n=1)
        if upfront:
            dims.update(_dim("EC2LINUX", pay, "Quantity", upfront, n=2))
        reserved.update(_term("EC2LINUX", f"R-{pay}", dims, {"LeaseContractLength": "1yr", "OfferingClass": "standard", "PurchaseOption": pay}))
    return build_offer("AmazonEC2", products, {s: _wrap(o) for s, o in _group(od).items()}, {"EC2LINUX": {**reserved}})


def _group(flat: dict) -> dict[str, dict]:
    """flat {'SKU.term': {...}} -> {'SKU': {'SKU.term': {...}}}"""
    out: dict[str, dict] = {}
    for key, value in flat.items():
        out.setdefault(key.split(".")[0], {})[key] = value
    return out


def _wrap(x):
    return x


def s3_offer() -> dict:
    def storage(sku, vt):
        return (sku, {"productFamily": "Storage", "attributes": {"volumeType": vt, "storageClass": vt, "usagetype": "APS3-TimedStorage-ByteHrs"}})

    def req(sku, usage):
        return (sku, {"productFamily": "API Request", "attributes": {"usagetype": usage, "group": "S3-API"}})

    products = [
        storage("STD", "Standard"), storage("SIA", "Standard - Infrequent Access"),
        req("PUT", "APS3-Requests-Tier1"), req("GET", "APS3-Requests-Tier2"),
        req("SIAPUT", "APS3-Requests-SIA-Tier1"), req("SIAGET", "APS3-Requests-SIA-Tier2"), req("SIARET", "APS3-Retrieval-SIA"),
        ("TAG", {"productFamily": "Storage", "attributes": {"volumeType": "Tags", "storageClass": "Tags", "usagetype": "APS3-TagStorage-TagHrs"}}),
    ]
    od: dict[str, dict] = {}
    std_dims = {}
    std_dims.update(_dim("STD", "OD", "GB-Mo", "0.0250000000", "0", "51200", 1))
    std_dims.update(_dim("STD", "OD", "GB-Mo", "0.0240000000", "51200", "512000", 2))
    std_dims.update(_dim("STD", "OD", "GB-Mo", "0.0230000000", "512000", "Inf", 3))
    od["STD"] = _term("STD", "OD", std_dims)
    for sku, unit, price in [("SIA", "GB-Mo", "0.0138000000"), ("PUT", "Requests", "0.0000050000"), ("GET", "Requests", "0.0000004000"),
                             ("SIAPUT", "Requests", "0.0000100000"), ("SIAGET", "Requests", "0.0000010000"), ("SIARET", "GB", "0.0100000000"),
                             ("TAG", "Tag-Mo", "0.0000006500")]:
        od[sku] = _term(sku, "OD", _dim(sku, "OD", unit, price))
    return build_offer("AmazonS3", products, od)


def rds_offer() -> dict:
    def inst(sku, deployment, engine="PostgreSQL"):
        return (sku, {"productFamily": "Database Instance", "attributes": {
            "instanceType": "db.t3.medium", "instanceFamily": "General purpose", "vcpu": "2", "memory": "4 GiB",
            "databaseEngine": engine, "licenseModel": "No license required", "deploymentOption": deployment,
            "regionCode": "ap-south-1", "currentGeneration": "Yes"}})

    def store(sku, vt, deployment):
        return (sku, {"productFamily": "Database Storage", "attributes": {"volumeType": vt, "deploymentOption": deployment, "databaseEngine": "PostgreSQL"}})

    def piops(sku, usage, deployment):
        return (sku, {"productFamily": "Provisioned IOPS", "attributes": {"usagetype": usage, "deploymentOption": deployment, "databaseEngine": "PostgreSQL"}})

    products = [
        inst("I-S", "Single-AZ"), inst("I-M", "Multi-AZ"), inst("I-AUR", "Single-AZ", engine="Aurora PostgreSQL"),
        inst("I-RS", "Multi-AZ (readable standbys)"),  # filtered out
        store("S-GP3-S", "General Purpose-GP3", "Single-AZ"), store("S-GP3-M", "General Purpose-GP3", "Multi-AZ"),
        store("S-IO1-S", "Provisioned IOPS", "Single-AZ"),
        piops("P-IO1-S", "APS3-RDS:PIOPS", "Single-AZ"), piops("P-IO2-S", "APS3-RDS:IO2-PIOPS", "Single-AZ"),
        piops("P-GP3-S", "APS3-RDS:GP3-PIOPS", "Single-AZ"),
    ]
    od = {}
    for sku, unit, price in [
        ("I-S", "Hrs", "0.1000000000"), ("I-M", "Hrs", "0.2000000000"), ("I-AUR", "Hrs", "0.3"), ("I-RS", "Hrs", "9"),
        ("S-GP3-S", "GB-Mo", "0.1300000000"), ("S-GP3-M", "GB-Mo", "0.2600000000"), ("S-IO1-S", "GB-Mo", "0.1500000000"),
        ("P-IO1-S", "IOPS-Mo", "0.1000000000"), ("P-IO2-S", "IOPS-Mo", "0.0900000000"), ("P-GP3-S", "IOPS-Mo", "0.0200000000"),
    ]:
        od[sku] = _term(sku, "OD", _dim(sku, "OD", unit, price))
    reserved = {"I-S": _term("I-S", "R", {**_dim("I-S", "R", "Hrs", "0.0400000000", n=1), **_dim("I-S", "R", "Quantity", "300", n=2)},
                             {"LeaseContractLength": "3yr", "OfferingClass": "standard", "PurchaseOption": "Partial Upfront"})}
    return build_offer("AmazonRDS", products, od, reserved)


def sp_offer() -> dict:
    """Savings Plans file shape: `products` is a LIST, terms are a list of plans whose
    `rates` point at EC2 SKUs via discountedSku."""
    plans = [
        # sku, family, term, option, hourly price for EC2LINUX
        ("SP-C1-N", "ComputeSavingsPlans", "1yr", "No Upfront", "0.0700000000"),
        ("SP-C1-P", "ComputeSavingsPlans", "1yr", "Partial Upfront", "0.0600000000"),
        ("SP-C1-A", "ComputeSavingsPlans", "1yr", "All Upfront", "0.0500000000"),
        ("SP-C3-N", "ComputeSavingsPlans", "3yr", "No Upfront", "0.0400000000"),
        ("SP-E1-N", "EC2InstanceSavingsPlans", "1yr", "No Upfront", "0.0600000000"),
    ]
    products = [
        {"sku": sku, "productFamily": fam, "attributes": {"purchaseTerm": term, "purchaseOption": opt}}
        for sku, fam, term, opt, _ in plans
    ]
    terms = []
    for sku, _fam, term, _opt, price in plans:
        terms.append({
            "sku": sku, "leaseContractLength": {"duration": int(term[0]), "unit": "year"},
            "rates": [
                {"discountedSku": "EC2LINUX", "unit": "Hrs", "rateCode": f"{sku}.EC2LINUX", "discountedRate": {"price": price, "currency": "USD"}},
                {"discountedSku": "EC2LINUX", "unit": "Quantity", "rateCode": f"{sku}.Q", "discountedRate": {"price": "999", "currency": "USD"}},  # not hourly: ignored
                {"discountedSku": "SOME-OTHER-SERVICE-SKU", "unit": "Hrs", "rateCode": f"{sku}.X", "discountedRate": {"price": "999", "currency": "USD"}},  # not ours: ignored
            ],
        })
    return {"version": "20260101000000", "publicationDate": "2026-01-01T00:00:00Z", "regionCode": "ap-south-1",
            "products": products, "terms": {"savingsPlan": terms}}


def dt_offer() -> dict:
    def prod(sku, ttype, frm, to, to_type="AWS Region", to_code=None):
        return (sku, {"productFamily": "Data Transfer", "attributes": {
            "transferType": ttype, "fromLocation": frm, "toLocation": to, "toLocationType": to_type,
            "fromRegionCode": "ap-south-1", "toRegionCode": to_code}})

    products = [
        prod("DTFREE", "AWS Outbound", "Global", "External", "External"),
        prod("DTOUT", "AWS Outbound", "Asia Pacific (Mumbai)", "External", "External"),
        prod("DTX", "IntraRegion", "Asia Pacific (Mumbai)", "Asia Pacific (Mumbai)"),
        prod("DTIR", "InterRegion Outbound", "Asia Pacific (Mumbai)", "US East (N. Virginia)", to_code="us-east-1"),
        prod("DTWL", "InterRegion Outbound", "Asia Pacific (Mumbai)", "Verizon Denver", "Wavelength Zone", to_code="us-west-2-wl1-den1"),
        prod("DTIN", "AWS Inbound", "External", "Asia Pacific (Mumbai)", "AWS Region"),
    ]
    out_dims = {}
    out_dims.update(_dim("DTOUT", "OD", "GB", "0.1000000000", "0", "10240", 1))
    out_dims.update(_dim("DTOUT", "OD", "GB", "0.0800000000", "10240", "51200", 2))
    out_dims.update(_dim("DTOUT", "OD", "GB", "0.0600000000", "51200", "Inf", 3))
    od = {
        "DTFREE": _term("DTFREE", "OD", _dim("DTFREE", "OD", "GB", "0.0000000000", "0", "100")),
        "DTOUT": _term("DTOUT", "OD", out_dims),
        "DTX": _term("DTX", "OD", _dim("DTX", "OD", "GB", "0.0100000000")),
        "DTIR": _term("DTIR", "OD", _dim("DTIR", "OD", "GB", "0.0800000000")),
        "DTWL": _term("DTWL", "OD", _dim("DTWL", "OD", "GB", "0.0800000000")),
        "DTIN": _term("DTIN", "OD", _dim("DTIN", "OD", "GB", "0.0000000000")),
    }
    return build_offer("AWSDataTransfer", products, od)


def write_offers(root: Path, region: str = "ap-south-1") -> dict[str, Path]:
    paths = {}
    for service, offer in (("ec2", ec2_offer()), ("sp", sp_offer()), ("s3", s3_offer()), ("rds", rds_offer()), ("dt", dt_offer())):
        p = root / f"{service}-{region}.json"
        p.write_text(json.dumps(offer), encoding="utf-8")
        paths[service] = p
    return paths
