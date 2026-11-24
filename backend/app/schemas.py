"""API contract (Pydantic). FastAPI turns these into validation + OpenAPI docs.

Money fields in *responses* are strings with 2 decimals ("1234.50") so that no
float ever touches a price; the UI formats them for display.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

Qty = Annotated[Decimal, Field(ge=0, le=Decimal("1e12"))]


# ----------------------------------------------------------------- inputs ---
class Pricing(BaseModel):
    """How the instance is bought. `term` and `payment` apply to Reserved and Savings Plans."""

    model: Literal["on_demand", "reserved", "savings_plan"] = "on_demand"
    offering_class: Literal["standard", "convertible"] = "standard"  # Reserved, EC2 only; RDS is always standard
    sp_type: Literal["compute", "ec2_instance"] = "compute"  # Savings Plan flavour (EC2 only)
    term: Literal["1yr", "3yr"] = "1yr"
    payment: Literal["no_upfront", "partial_upfront", "all_upfront"] = "no_upfront"


class Usage(BaseModel):
    """How much of the month an On-Demand instance runs (Reserved always bills 730 h)."""

    mode: Literal["always", "percent_month", "hours_per_day"] = "always"
    percent: Annotated[Decimal, Field(ge=0, le=100)] = Decimal(100)
    hours_per_day: Annotated[Decimal, Field(ge=0, le=24)] = Decimal(24)
    days_per_week: Annotated[Decimal, Field(ge=0, le=7)] = Decimal(7)


class EbsVolume(BaseModel):
    volume_type: Literal["gp3", "gp2", "io1", "io2", "st1", "sc1"] = "gp3"
    size_gb: Annotated[Decimal, Field(gt=0, le=Decimal("65536"))] = Decimal(30)
    iops: Annotated[Decimal, Field(ge=0, le=Decimal("256000"))] | None = None
    throughput_mbps: Annotated[Decimal, Field(ge=0, le=Decimal("2000"))] | None = None
    snapshots_per_month: Annotated[int, Field(ge=0, le=744)] = 0
    snapshot_changed_gb: Qty = Decimal(0)  # data changed between two snapshots


class Ec2Item(BaseModel):
    type: Literal["ec2"] = "ec2"
    name: str = "EC2 instances"
    region: str
    instance_type: str
    os: str = "Linux"
    quantity: Annotated[int, Field(ge=1, le=100000)] = 1
    pricing: Pricing = Pricing()
    usage: Usage = Usage()
    ebs: list[EbsVolume] = Field(default_factory=list, max_length=20)  # volumes PER instance


class S3Item(BaseModel):
    type: Literal["s3"] = "s3"
    name: str = "S3 bucket"
    region: str
    storage_class: Literal["standard", "standard_ia", "onezone_ia", "glacier_ir"] = "standard"
    storage_gb: Qty = Decimal(100)
    put_requests: Qty = Decimal(0)  # PUT, COPY, POST, LIST per month
    get_requests: Qty = Decimal(0)  # GET, SELECT and other per month
    retrieval_gb: Qty = Decimal(0)  # data retrieved from IA / Glacier classes


class RdsItem(BaseModel):
    type: Literal["rds"] = "rds"
    name: str = "RDS database"
    region: str
    engine: str = "PostgreSQL"
    edition: str = ""
    license_model: str = "No license required"
    instance_type: str
    deployment: Literal["single_az", "multi_az"] = "single_az"
    quantity: Annotated[int, Field(ge=1, le=1000)] = 1
    pricing: Pricing = Pricing()
    usage: Usage = Usage()
    storage_type: Literal["gp2", "gp3", "io1", "io2"] = "gp3"
    storage_gb: Annotated[Decimal, Field(gt=0, le=Decimal("65536"))] = Decimal(100)
    iops: Annotated[Decimal, Field(ge=0, le=Decimal("256000"))] | None = None


class DataTransferItem(BaseModel):
    type: Literal["dt"] = "dt"
    name: str = "Data transfer"
    region: str  # the region the data leaves from
    internet_out_gb: Qty = Decimal(0)  # to the public internet, per month
    inter_region_gb: Qty = Decimal(0)  # to another AWS region
    destination_region: str | None = None
    cross_az_gb: Qty = Decimal(0)  # between availability zones inside the region
    apply_free_tier: bool = True  # first 100 GB/month to the internet is free (once per AWS account)


LineItem = Annotated[Union[Ec2Item, S3Item, RdsItem, DataTransferItem], Field(discriminator="type")]


class Scenario(BaseModel):
    name: str = Field("My estimate", min_length=1, max_length=120)
    items: list[LineItem] = Field(default_factory=list, max_length=200)


class CompareRequest(BaseModel):
    scenarios: list[Scenario] = Field(min_length=2, max_length=4)


# ---------------------------------------------------------------- outputs ---
class Component(BaseModel):
    label: str
    quantity: str
    unit: str
    monthly: str
    upfront: str = "0.00"
    explain: list[str] = Field(default_factory=list)  # the maths, line by line


class ItemResult(BaseModel):
    name: str
    type: str
    region: str
    summary: str
    components: list[Component]
    monthly: str
    upfront: str
    first_12_months: str
    effective_monthly: str  # monthly + upfront spread over the commitment term
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class EstimateResult(BaseModel):
    name: str
    currency: str = "USD"
    items: list[ItemResult]
    monthly: str
    yearly: str  # monthly x 12 (recurring only)
    upfront: str
    first_12_months: str  # monthly x 12 + upfront  (the calculator's "Total 12 months cost")
    effective_monthly: str
    price_list_dates: dict[str, str]
    assumptions: list[str]


class ScenarioDiff(BaseModel):
    name: str
    monthly: str
    first_12_months: str
    effective_monthly: str
    vs_baseline: str  # signed difference in effective monthly cost
    vs_baseline_pct: str


class CompareResult(BaseModel):
    baseline: str
    scenarios: list[EstimateResult]
    diffs: list[ScenarioDiff]
    cheapest: str


class SavedScenario(BaseModel):
    id: str
    name: str
    scenario: Scenario
    created_at: str
    updated_at: str
