import type {
  Alternatives,
  CompareResult,
  DtCatalog,
  Ec2Catalog,
  EstimateResult,
  Meta,
  RdsCatalog,
  S3Catalog,
  SavedScenario,
  Scenario,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** FastAPI returns {detail: string} or {detail: [{loc, msg}, ...]} for 422s. */
function describe(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { loc?: (string | number)[]; msg?: string }
    const where = (first.loc ?? []).filter((p) => p !== 'body').join(' > ')
    return `${where ? where + ': ' : ''}${first.msg ?? 'invalid value'}`
  }
  return 'Unexpected error'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, describe((body as { detail?: unknown }).detail))
  return body as T
}

const json = (method: string, data: unknown, signal?: AbortSignal): RequestInit => ({
  method,
  body: JSON.stringify(data),
  signal,
})

export const api = {
  meta: () => request<Meta>('/api/meta'),
  ec2Catalog: (region: string) => request<Ec2Catalog>(`/api/catalog/ec2?region=${encodeURIComponent(region)}`),
  rdsCatalog: (region: string) => request<RdsCatalog>(`/api/catalog/rds?region=${encodeURIComponent(region)}`),
  dtCatalog: (region: string) => request<DtCatalog>(`/api/catalog/dt?region=${encodeURIComponent(region)}`),
  alternatives: (region: string, instanceType: string, os: string) =>
    request<Alternatives>(
      `/api/ec2/alternatives?region=${encodeURIComponent(region)}&instance_type=${encodeURIComponent(instanceType)}&os=${encodeURIComponent(os)}`,
    ),
  s3Catalog: () => request<S3Catalog>('/api/catalog/s3'),
  estimate: (s: Scenario, signal?: AbortSignal) => request<EstimateResult>('/api/estimate', json('POST', s, signal)),
  compare: (scenarios: Scenario[]) => request<CompareResult>('/api/compare', json('POST', { scenarios })),
  listSaved: () => request<SavedScenario[]>('/api/scenarios'),
  createSaved: (s: Scenario) => request<SavedScenario>('/api/scenarios', json('POST', s)),
  updateSaved: (id: string, s: Scenario) => request<SavedScenario>(`/api/scenarios/${id}`, json('PUT', s)),
  deleteSaved: (id: string) => request<void>(`/api/scenarios/${id}`, { method: 'DELETE' }),
}
