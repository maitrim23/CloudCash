import type { DataTransferItem, EbsVolume, Ec2Item, Pricing, RdsItem, S3Item, Usage } from './types'

export const defaultPricing = (): Pricing => ({
  model: 'on_demand',
  offering_class: 'standard',
  sp_type: 'compute',
  term: '1yr',
  payment: 'no_upfront',
})

export const defaultUsage = (): Usage => ({ mode: 'always', percent: 100, hours_per_day: 24, days_per_week: 7 })

export const newVolume = (): EbsVolume => ({
  volume_type: 'gp3',
  size_gb: 30,
  iops: null,
  throughput_mbps: null,
  snapshots_per_month: 0,
  snapshot_changed_gb: 0,
})

export const newEc2 = (region: string): Ec2Item => ({
  type: 'ec2',
  name: 'EC2 instances',
  region,
  instance_type: 't3.medium',
  os: 'Linux',
  quantity: 1,
  pricing: defaultPricing(),
  usage: defaultUsage(),
  ebs: [newVolume()],
})

export const newS3 = (region: string): S3Item => ({
  type: 's3',
  name: 'S3 bucket',
  region,
  storage_class: 'standard',
  storage_gb: 100,
  put_requests: 0,
  get_requests: 0,
  retrieval_gb: 0,
})

export const newDt = (region: string): DataTransferItem => ({
  type: 'dt',
  name: 'Data transfer',
  region,
  internet_out_gb: 500,
  inter_region_gb: 0,
  destination_region: null,
  cross_az_gb: 0,
  apply_free_tier: true,
})

export const newRds = (region: string): RdsItem => ({
  type: 'rds',
  name: 'RDS database',
  region,
  engine: 'PostgreSQL',
  edition: '',
  license_model: 'No license required',
  instance_type: 'db.t3.medium',
  deployment: 'single_az',
  quantity: 1,
  pricing: defaultPricing(),
  usage: defaultUsage(),
  storage_type: 'gp3',
  storage_gb: 100,
  iops: null,
})
