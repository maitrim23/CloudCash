const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

/** "1234.5" -> "$1,234.50". Server money is already rounded to cents. */
export function money(value: string | number): string {
  const n = typeof value === 'string' ? Number(value) : value
  return Number.isFinite(n) ? usd.format(n) : '—'
}

/** Signed difference: "+$12.00" / "-$12.00" / "$0.00". */
export function signedMoney(value: string): string {
  const n = Number(value)
  if (!Number.isFinite(n) || n === 0) return money(0)
  return `${n > 0 ? '+' : '-'}${usd.format(Math.abs(n))}`
}

export function signedPercent(value: string): string {
  const n = Number(value)
  if (!Number.isFinite(n) || n === 0) return '0%'
  return `${n > 0 ? '+' : '-'}${Math.abs(n).toFixed(1)}%`
}

export const REGION_NAMES: Record<string, string> = {
  'us-east-1': 'US East (N. Virginia)',
  'us-east-2': 'US East (Ohio)',
  'us-west-2': 'US West (Oregon)',
  'eu-west-1': 'Europe (Ireland)',
  'eu-central-1': 'Europe (Frankfurt)',
  'ap-south-1': 'Asia Pacific (Mumbai)',
  'ap-southeast-1': 'Asia Pacific (Singapore)',
  'ap-northeast-1': 'Asia Pacific (Tokyo)',
}

export const regionLabel = (code: string) => (REGION_NAMES[code] ? `${REGION_NAMES[code]} · ${code}` : code)
