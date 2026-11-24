// Mirrors backend/app/schemas.py. Money in responses is a string ("1234.50").

export type Pricing = {
  model: 'on_demand' | 'reserved' | 'savings_plan'
  offering_class: 'standard' | 'convertible'
  sp_type: 'compute' | 'ec2_instance'
  term: '1yr' | '3yr'
  payment: 'no_upfront' | 'partial_upfront' | 'all_upfront'
}

export type Usage = {
  mode: 'always' | 'percent_month' | 'hours_per_day'
  percent: number
  hours_per_day: number
  days_per_week: number
}

export type EbsVolume = {
  volume_type: 'gp3' | 'gp2' | 'io1' | 'io2' | 'st1' | 'sc1'
  size_gb: number
  iops: number | null
  throughput_mbps: number | null
  snapshots_per_month: number
  snapshot_changed_gb: number
}

export type Ec2Item = {
  type: 'ec2'
  name: string
  region: string
  instance_type: string
  os: string
  quantity: number
  pricing: Pricing
  usage: Usage
  ebs: EbsVolume[]
}

export type S3Class = 'standard' | 'standard_ia' | 'onezone_ia' | 'glacier_ir'

export type S3Item = {
  type: 's3'
  name: string
  region: string
  storage_class: S3Class
  storage_gb: number
  put_requests: number
  get_requests: number
  retrieval_gb: number
}

export type RdsItem = {
  type: 'rds'
  name: string
  region: string
  engine: string
  edition: string
  license_model: string
  instance_type: string
  deployment: 'single_az' | 'multi_az'
  quantity: number
  pricing: Pricing
  usage: Usage
  storage_type: 'gp2' | 'gp3' | 'io1' | 'io2'
  storage_gb: number
  iops: number | null
}

export type DataTransferItem = {
  type: 'dt'
  name: string
  region: string
  internet_out_gb: number
  inter_region_gb: number
  destination_region: string | null
  cross_az_gb: number
  apply_free_tier: boolean
}

export type LineItem = Ec2Item | S3Item | RdsItem | DataTransferItem
export type Scenario = { name: string; items: LineItem[] }

export type Component = {
  label: string
  quantity: string
  unit: string
  monthly: string
  upfront: string
  explain: string[]
}

export type ItemResult = {
  name: string
  type: string
  region: string
  summary: string
  components: Component[]
  monthly: string
  upfront: string
  first_12_months: string
  effective_monthly: string
  warnings: string[]
  error: string | null
}

export type EstimateResult = {
  name: string
  currency: string
  items: ItemResult[]
  monthly: string
  yearly: string
  upfront: string
  first_12_months: string
  effective_monthly: string
  price_list_dates: Record<string, string>
  assumptions: string[]
}

export type ScenarioDiff = {
  name: string
  monthly: string
  first_12_months: string
  effective_monthly: string
  vs_baseline: string
  vs_baseline_pct: string
}

export type CompareResult = {
  baseline: string
  scenarios: EstimateResult[]
  diffs: ScenarioDiff[]
  cheapest: string
}

export type SavedScenario = {
  id: string
  name: string
  scenario: Scenario
  created_at: string
  updated_at: string
}

export type Meta = { regions: { region: string; price_list_dates: Record<string, string> }[] }

export type Ec2Catalog = {
  region: string
  instances: {
    instance_type: string
    family: string | null
    vcpu: string | null
    memory: string | null
    network: string | null
    current_generation: boolean
    os: string[]
  }[]
}

export type RdsCatalog = {
  region: string
  engines: { engine: string; edition: string; license_model: string }[]
  instances: { instance_type: string; vcpu: string | null; memory: string | null; combos: string[] }[]
}

export type DtCatalog = { region: string; destinations: { region: string; name: string }[] }

export type Alternatives = {
  instance_type: string
  hourly: string
  alternatives: { instance_type: string; vcpu: number; memory_gib: string; hourly: string; saving_pct: string; arm: boolean }[]
}

export type S3Catalog = { storage_classes: { id: S3Class; label: string }[] }
