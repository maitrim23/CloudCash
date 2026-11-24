-- Price database: written by app.pricing.ingest, read-only at request time.
--
-- Three tables:
--   meta    : which AWS price-list version each (service, region) came from
--   product : what can be priced (drives dropdowns, carries specs like vCPU)
--   rate    : the actual prices, one row per price *dimension* (a tier, an hourly
--             fee, an upfront fee ...). Tiered prices are several rows.

CREATE TABLE IF NOT EXISTS meta (
    service          TEXT NOT NULL,
    region           TEXT NOT NULL,
    version          TEXT NOT NULL,
    publication_date TEXT NOT NULL,
    ingested_at      TEXT NOT NULL,
    product_count    INTEGER NOT NULL,
    rate_count       INTEGER NOT NULL,
    PRIMARY KEY (service, region)
);

CREATE TABLE IF NOT EXISTS product (
    service TEXT NOT NULL,
    region  TEXT NOT NULL,
    family  TEXT NOT NULL,   -- ec2_instance, ebs_storage, s3_storage, rds_instance ...
    key     TEXT NOT NULL,   -- canonical lookup key, see ingest.py normalizers
    attrs   TEXT NOT NULL,   -- JSON: the AWS attributes worth keeping
    PRIMARY KEY (service, region, family, key)
);

CREATE TABLE IF NOT EXISTS rate (
    service  TEXT NOT NULL,
    region   TEXT NOT NULL,
    family   TEXT NOT NULL,
    key      TEXT NOT NULL,
    term     TEXT NOT NULL,  -- OnDemand | Reserved
    lease    TEXT NOT NULL DEFAULT '',   -- 1yr | 3yr (Reserved only)
    offering TEXT NOT NULL DEFAULT '',   -- standard | convertible (Reserved only)
    payment  TEXT NOT NULL DEFAULT '',   -- No Upfront | Partial Upfront | All Upfront
    unit     TEXT NOT NULL,              -- Hrs, GB-Mo, Quantity (= upfront fee), Requests ...
    begin    TEXT NOT NULL,              -- tier start, as text to keep Decimal exact
    "end"    TEXT,                       -- tier end; NULL = Inf
    price    TEXT NOT NULL,              -- USD, as text
    sku      TEXT NOT NULL,
    rate_code TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rate_lookup ON rate (service, region, family, key, term);
