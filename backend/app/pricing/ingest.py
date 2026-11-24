"""Offline ingest: AWS price-list files  ->  small SQLite price database.

Usage (from backend/):
    python -m app.pricing.ingest --regions ap-south-1 --services s3 rds ec2
    python -m app.pricing.ingest --regions ap-south-1 us-east-1 --download

Why offline? The EC2 price list for ONE region is ~315 MB of JSON. We stream it
once (ijson, constant memory), keep only the product families this app can price,
and write a database that is a few MB. The API never touches the big files.

Source: the documented public bulk price list
    https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<OfferCode>/current/<region>/index.json
No AWS account or credentials are needed.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

import ijson

from .store import connect, init_schema

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OFFER_DIR = DATA_DIR / "offers"
DEFAULT_DB = DATA_DIR / "prices.db"

OFFER_CODES = {"ec2": "AmazonEC2", "sp": "AWSComputeSavingsPlan", "s3": "AmazonS3", "rds": "AmazonRDS", "dt": "AWSDataTransfer"}
BASE_URL = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{offer}/current/{region}/index.json"
PRICING_HOST = "https://pricing.us-east-1.amazonaws.com"
# Savings Plans live under a different path and need a region index to find the versioned file.
SP_INDEX_URL = PRICING_HOST + "/savingsPlan/v1.0/aws/AWSComputeSavingsPlan/current/region_index.json"

# --------------------------------------------------------------------------
# Normalizers: decide which AWS products we keep and under which (family, key).
# Each returns None (skip) or (family, key, attrs-to-keep).
# --------------------------------------------------------------------------
Normalized = tuple[str, str, dict] | None

EBS_VOLUME_API_NAMES = {"gp2", "gp3", "io1", "io2", "st1", "sc1", "standard"}
_REGION_PREFIX = re.compile(r"^[A-Z]{2,5}\d-")


def strip_region_prefix(usagetype: str) -> str:
    """'APS3-Requests-Tier1' -> 'Requests-Tier1' (us-east-1 has no prefix)."""
    return _REGION_PREFIX.sub("", usagetype)


def normalize_ec2(p: dict) -> Normalized:
    a = p.get("attributes", {})
    fam = p.get("productFamily")
    if fam == "Compute Instance":
        if (
            a.get("tenancy") == "Shared"
            and a.get("capacitystatus") == "Used"
            and a.get("preInstalledSw") == "NA"
            and a.get("operatingSystem") not in (None, "NA")
            and a.get("licenseModel") in ("No License required", "NA", None)
        ):
            keep = {
                k: a.get(k)
                for k in (
                    "instanceType", "instanceFamily", "vcpu", "memory", "storage",
                    "networkPerformance", "physicalProcessor", "currentGeneration",
                    "operatingSystem", "regionCode", "location",
                )
            }
            return "ec2_instance", f"{a['instanceType']}|{a['operatingSystem']}", keep
        return None
    if fam == "Storage" and a.get("volumeApiName") in EBS_VOLUME_API_NAMES:
        keep = {"volumeApiName": a["volumeApiName"], "volumeType": a.get("volumeType"), "maxVolumeSize": a.get("maxVolumeSize")}
        return "ebs_storage", a["volumeApiName"], keep
    if fam == "System Operation" and a.get("volumeApiName") in EBS_VOLUME_API_NAMES and "IOPS" in (a.get("group") or ""):
        # io2 IOPS are tiered, and AWS publishes each tier as its own SKU whose
        # range is 0-Inf. The usagetype ends in ".tier2" / ".tier3" (tier 1 has no suffix).
        api = a["volumeApiName"]
        m = re.search(r"\.tier(\d)$", a.get("usagetype") or "")
        key = f"{api}:tier{m.group(1)}" if m else (f"{api}:tier1" if api == "io2" else api)
        return "ebs_iops", key, {"volumeApiName": api, "group": a.get("group")}
    if fam == "Provisioned Throughput" and a.get("volumeApiName") in EBS_VOLUME_API_NAMES:
        return "ebs_throughput", a["volumeApiName"], {"volumeApiName": a["volumeApiName"]}
    if fam == "Storage Snapshot" and (a.get("usagetype") or "").endswith("EBS:SnapshotUsage"):
        return "ebs_snapshot", "standard", {"usagetype": a.get("usagetype")}
    return None


def normalize_s3(p: dict) -> Normalized:
    a = p.get("attributes", {})
    fam = p.get("productFamily")
    if fam == "Storage" and a.get("volumeType") and a.get("storageClass") not in ("Tags",):
        return "s3_storage", a["volumeType"], {"volumeType": a["volumeType"], "storageClass": a.get("storageClass"), "durability": a.get("durability"), "availability": a.get("availability")}
    if fam == "API Request" and a.get("usagetype"):
        return "s3_request", strip_region_prefix(a["usagetype"]), {"usagetype": a["usagetype"], "group": a.get("group")}
    return None


def normalize_rds(p: dict) -> Normalized:
    a = p.get("attributes", {})
    fam = p.get("productFamily")
    if fam == "Database Instance" and a.get("deploymentOption") in ("Single-AZ", "Multi-AZ"):
        key = "|".join(
            [a["instanceType"], a["databaseEngine"], a.get("databaseEdition") or "", a.get("licenseModel") or "", a["deploymentOption"]]
        )
        keep = {
            k: a.get(k)
            for k in (
                "instanceType", "instanceFamily", "vcpu", "memory", "storage", "networkPerformance",
                "databaseEngine", "databaseEdition", "licenseModel", "deploymentOption", "currentGeneration",
            )
        }
        return "rds_instance", key, keep
    if fam == "Database Storage" and a.get("deploymentOption") in ("Single-AZ", "Multi-AZ"):
        key = "|".join([a.get("volumeType") or "", a["deploymentOption"], a.get("databaseEngine") or ""])
        return "rds_storage", key, {"volumeType": a.get("volumeType"), "deploymentOption": a["deploymentOption"], "databaseEngine": a.get("databaseEngine")}
    if fam == "Provisioned IOPS" and a.get("deploymentOption") in ("Single-AZ", "Multi-AZ"):
        # volumeType is blank on IOPS rows (gp3 and io1); the usagetype tells io1/io2/gp3 apart:
        #   RDS:PIOPS, RDS:IO2-PIOPS, RDS:GP3-PIOPS (+ a Multi-AZ- variant of each)
        usage = a.get("usagetype") or ""
        kind = "io2" if "IO2-PIOPS" in usage else "gp3" if "GP3-PIOPS" in usage else "io1"
        key = "|".join([kind, a["deploymentOption"], a.get("databaseEngine") or ""])
        return "rds_iops", key, {"kind": kind, "deploymentOption": a["deploymentOption"], "databaseEngine": a.get("databaseEngine")}
    return None


def normalize_dt(p: dict) -> Normalized:
    """AWSDataTransfer offer. Data IN is free (not modelled). We keep:
       dt_internet_out  graduated per-GB tiers from this region to the internet
       dt_free          the global free allowance (first 100 GB/month); its endRange IS the allowance
       dt_interregion   per-GB price to each destination AWS region (key = destination region code)
       dt_cross_az      per-GB price between availability zones (billed in EACH direction)"""
    a = p.get("attributes", {})
    t, frm, to = a.get("transferType"), a.get("fromLocation"), a.get("toLocation")
    if t == "AWS Outbound" and to == "External":
        if frm == "Global":
            return "dt_free", "internet_out", {"scope": "global"}
        return "dt_internet_out", "internet", {"from": frm}
    if t == "InterRegion Outbound" and a.get("toLocationType") == "AWS Region" and a.get("toRegionCode"):
        return "dt_interregion", a["toRegionCode"], {"to_region": a["toRegionCode"], "to_name": to}
    if t == "IntraRegion" and frm == to and frm != "Global":
        return "dt_cross_az", "cross_az", {"location": frm}
    return None


NORMALIZERS: dict[str, Callable[[dict], Normalized]] = {
    "dt": normalize_dt,
    "ec2": normalize_ec2,
    "s3": normalize_s3,
    "rds": normalize_rds,
}
# Reserved terms are big; only fetch them for the families people reserve.
RESERVED_FAMILIES = {"ec2_instance", "rds_instance"}


# --------------------------------------------------------------------------
# Streaming
# --------------------------------------------------------------------------
def _header(path: Path) -> dict:
    """version / publicationDate sit before `products`, so this reads a few bytes."""
    out: dict = {}
    with path.open("rb") as f:
        for prefix, event, value in ijson.parse(f):
            if prefix in ("version", "publicationDate"):
                out[prefix] = value
            if prefix == "products":
                break
    return out


def _stream_products(path: Path, normalizer) -> dict[str, tuple[str, str, dict]]:
    wanted: dict[str, tuple[str, str, dict]] = {}
    with path.open("rb") as f:
        for sku, product in ijson.kvitems(f, "products"):
            norm = normalizer(product)
            if norm:
                wanted[sku] = norm
    return wanted


def _stream_terms(path: Path, term_type: str, wanted: dict) -> Iterator[tuple[str, dict]]:
    with path.open("rb") as f:
        for sku, offers in ijson.kvitems(f, f"terms.{term_type}"):
            if sku in wanted:
                for offer in offers.values():
                    yield sku, offer


def ingest_file(conn: sqlite3.Connection, service: str, region: str, path: Path) -> tuple[int, int]:
    header = _header(path)
    wanted = _stream_products(path, NORMALIZERS[service])

    # Several SKUs can normalize to the same (family, key) (e.g. duplicate listings).
    # Keep the first SKU we see per key and ignore the others' rates.
    primary_sku: dict[tuple[str, str], str] = {}
    for sku, (family, key, _attrs) in wanted.items():
        primary_sku.setdefault((family, key), sku)

    conn.execute("DELETE FROM product WHERE service = ? AND region = ?", (service, region))
    conn.execute("DELETE FROM rate WHERE service = ? AND region = ?", (service, region))
    if service == "ec2":  # Savings Plans rates hang off EC2 SKUs we just deleted: re-run `sp` after this.
        conn.execute("DELETE FROM meta WHERE service = 'ec2sp' AND region = ?", (region,))

    products = 0
    for (family, key), sku in primary_sku.items():
        conn.execute(
            "INSERT INTO product (service, region, family, key, attrs) VALUES (?,?,?,?,?)",
            (service, region, family, key, json.dumps(wanted[sku][2])),
        )
        products += 1

    rates = 0
    for term_type in ("OnDemand", "Reserved"):
        for sku, offer in _stream_terms(path, term_type, wanted):
            family, key, _ = wanted[sku]
            if primary_sku[(family, key)] != sku:
                continue
            if term_type == "Reserved" and family not in RESERVED_FAMILIES:
                continue
            ta = offer.get("termAttributes", {})
            lease = ta.get("LeaseContractLength", "") if term_type == "Reserved" else ""
            offering = (ta.get("OfferingClass", "") if term_type == "Reserved" else "").lower()
            payment = ta.get("PurchaseOption", "") if term_type == "Reserved" else ""
            for dim in offer["priceDimensions"].values():
                usd = dim["pricePerUnit"].get("USD")
                if usd is None:
                    continue
                end = dim.get("endRange")
                conn.execute(
                    'INSERT INTO rate (service, region, family, key, term, lease, offering, payment, unit, begin, "end", price, sku, rate_code) '
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        service, region, family, key, term_type, lease, offering, payment,
                        dim["unit"], dim.get("beginRange") or "0", None if end in (None, "Inf") else end,
                        usd, sku, dim["rateCode"],
                    ),
                )
                rates += 1

    quality_gate(conn, service, region)

    conn.execute(
        "INSERT OR REPLACE INTO meta (service, region, version, publication_date, ingested_at, product_count, rate_count) VALUES (?,?,?,?,?,?,?)",
        (service, region, header.get("version", ""), header.get("publicationDate", ""),
         datetime.now(timezone.utc).isoformat(timespec="seconds"), products, rates),
    )
    conn.commit()
    return products, rates


SP_OFFERING = {"ComputeSavingsPlans": "compute", "EC2InstanceSavingsPlans": "ec2instance"}


def ingest_savings_plans(conn: sqlite3.Connection, region: str, path: Path) -> int:
    """Add Savings Plans rates to EC2 instances already in the database.

    A Savings Plans term lists, for every EC2 usage it covers, the discounted
    hourly rate keyed by `discountedSku` - the SAME sku as the On-Demand product.
    So we join on sku instead of parsing usage-type strings. The rate AWS publishes
    is the *effective* hourly rate (an all-upfront plan still shows a non-zero rate).
    """
    sku_key = {
        r["sku"]: (r["family"], r["key"])
        for r in conn.execute(
            "SELECT DISTINCT sku, family, key FROM rate WHERE service='ec2' AND region=? AND term='OnDemand' AND family='ec2_instance'",
            (region,),
        )
    }
    if not sku_key:
        raise RuntimeError(f"No EC2 prices for {region}: ingest 'ec2' before 'sp'.")

    plans: dict[str, tuple[str, str, str]] = {}  # plan sku -> (offering, lease, payment)
    with path.open("rb") as f:
        for p in ijson.items(f, "products.item"):
            a = p.get("attributes", {})
            offering = SP_OFFERING.get(p.get("productFamily", ""))
            if offering and a.get("purchaseTerm") and a.get("purchaseOption"):
                plans[p["sku"]] = (offering, a["purchaseTerm"], a["purchaseOption"])

    conn.execute("DELETE FROM rate WHERE service='ec2' AND region=? AND term='SavingsPlan'", (region,))
    header = _header_sp(path)
    count = 0
    with path.open("rb") as f:
        for term in ijson.items(f, "terms.savingsPlan.item"):
            plan = plans.get(term["sku"])
            if not plan:
                continue
            offering, lease, payment = plan
            for r in term["rates"]:
                hit = sku_key.get(r.get("discountedSku"))
                if not hit or r.get("unit") != "Hrs":
                    continue
                family, key = hit
                conn.execute(
                    'INSERT INTO rate (service, region, family, key, term, lease, offering, payment, unit, begin, "end", price, sku, rate_code) '
                    "VALUES ('ec2',?,?,?,'SavingsPlan',?,?,?,'Hrs','0',NULL,?,?,?)",
                    (region, family, key, lease, offering, payment, str(r["discountedRate"]["price"]), r["discountedSku"], r["rateCode"]),
                )
                count += 1
    if count == 0:
        conn.rollback()
        raise RuntimeError("Data-quality gate failed for sp: no Savings Plans rates matched any EC2 SKU")
    conn.execute(
        "INSERT OR REPLACE INTO meta (service, region, version, publication_date, ingested_at, product_count, rate_count) VALUES ('ec2sp',?,?,?,?,?,?)",
        (region, header.get("version", ""), header.get("publicationDate", ""), datetime.now(timezone.utc).isoformat(timespec="seconds"), len(plans), count),
    )
    conn.commit()
    return count


def _header_sp(path: Path) -> dict:
    """Savings Plans files put version/publicationDate AFTER products, so scan top-level scalars."""
    out: dict = {}
    with path.open("rb") as f:
        for prefix, event, value in ijson.parse(f):
            if prefix in ("version", "publicationDate"):
                out[prefix] = value
            if len(out) == 2:
                break
    return out


REQUIRED_FAMILIES = {
    "ec2": ["ec2_instance", "ebs_storage"],
    "s3": ["s3_storage", "s3_request"],
    "rds": ["rds_instance", "rds_storage"],
    "dt": ["dt_internet_out", "dt_interregion"],
}  # ('sp' has its own check inside ingest_savings_plans)


def quality_gate(conn: sqlite3.Connection, service: str, region: str) -> None:
    """Refuse to publish a database that is obviously broken (e.g. AWS changed the
    file format and the normalizers silently matched nothing). Raises -> ingest aborts
    and the transaction is rolled back, leaving the previous good data in place."""
    problems = []
    for family in REQUIRED_FAMILIES[service]:
        n = conn.execute("SELECT COUNT(*) FROM product WHERE service=? AND region=? AND family=?", (service, region, family)).fetchone()[0]
        if n == 0:
            problems.append(f"no '{family}' products")
    negative = conn.execute("SELECT COUNT(*) FROM rate WHERE service=? AND region=? AND CAST(price AS REAL) < 0", (service, region)).fetchone()[0]
    if negative:
        problems.append(f"{negative} negative prices")
    unpriced = conn.execute(
        "SELECT COUNT(*) FROM product p WHERE service=? AND region=? AND NOT EXISTS "
        "(SELECT 1 FROM rate r WHERE r.service=p.service AND r.region=p.region AND r.family=p.family AND r.key=p.key)",
        (service, region),
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM product WHERE service=? AND region=?", (service, region)).fetchone()[0]
    if total and unpriced / total > 0.2:
        problems.append(f"{unpriced}/{total} products have no price")
    if problems:
        conn.rollback()
        raise RuntimeError(f"Data-quality gate failed for {service}/{region}: " + "; ".join(problems))


def offer_path(service: str, region: str) -> Path:
    return OFFER_DIR / OFFER_CODES[service] / f"{region}.json"


def _sp_url(region: str) -> str:
    req = urllib.request.Request(SP_INDEX_URL, headers={"User-Agent": "cloud-cost-calculator-learning-project/0.1"})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_S) as resp:
        index = json.load(resp)
    for r in index["regions"]:
        if r["regionCode"] == region:
            return PRICING_HOST + r["versionUrl"]
    raise RuntimeError(f"No Savings Plans price list for region {region}")


DOWNLOAD_TIMEOUT_S = 60  # per socket read, not for the whole file: a stalled connection fails fast
DOWNLOAD_ATTEMPTS = 3


def download(service: str, region: str) -> Path:
    """Fetch an offer file. Written to `<name>.part` and renamed only when complete, so an
    interrupted download can never be mistaken for a finished file by the next run."""
    path = offer_path(service, region)
    path.parent.mkdir(parents=True, exist_ok=True)
    url = _sp_url(region) if service == "sp" else BASE_URL.format(offer=OFFER_CODES[service], region=region)
    part = path.with_name(path.name + ".part")
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        print(f"  downloading {url} (attempt {attempt}/{DOWNLOAD_ATTEMPTS})", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "cloud-cost-calculator-learning-project/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_S) as resp, part.open("wb") as out:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
            part.replace(path)
            return path
        except OSError as exc:  # URLError, socket.timeout and ConnectionError are all OSErrors
            print(f"  download failed: {exc}", flush=True)
            part.unlink(missing_ok=True)
    raise RuntimeError(f"Could not download {url} after {DOWNLOAD_ATTEMPTS} attempts")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regions", nargs="+", default=["ap-south-1"])
    ap.add_argument("--services", nargs="+", default=list(OFFER_CODES), choices=list(OFFER_CODES))
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--download", action="store_true", help="fetch files that are not on disk yet")
    args = ap.parse_args(argv)

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(args.db)
    init_schema(conn)
    for region in args.regions:
        for service in args.services:
            path = offer_path(service, region)
            if not path.exists():
                if not args.download:
                    print(f"skip {service}/{region}: {path} missing (use --download)")
                    continue
                download(service, region)
            print(f"ingesting {service}/{region} ...", flush=True)
            if service == "sp":
                print(f"  -> {ingest_savings_plans(conn, region, path)} Savings Plans rates")
            else:
                products, rates = ingest_file(conn, service, region, path)
                print(f"  -> {products} products, {rates} rates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
