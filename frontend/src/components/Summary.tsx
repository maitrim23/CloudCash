import { money } from '../format'
import type { EstimateResult } from '../types'

export function Summary({ result, loading, error }: { result: EstimateResult | null; loading: boolean; error: string | null }) {
  return (
    <aside aria-label="Estimate summary" className="sticky top-4 space-y-4 rounded-xl border border-line bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Estimate summary</h2>
        {loading && <span className="text-xs text-slate-400">updating…</span>}
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-red-50 p-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {!result ? (
        <p className="text-sm text-slate-500">Add a service to see your estimate.</p>
      ) : (
        <>
          <dl className="space-y-3">
            <Row label="Monthly cost" value={money(result.monthly)} big />
            <Row label="Yearly cost (recurring)" value={money(result.yearly)} />
            <Row label="Upfront cost" value={money(result.upfront)} />
            <Row label="First 12 months" value={money(result.first_12_months)} hint="monthly × 12 + upfront" />
            {Number(result.upfront) > 0 && (
              <Row label="Effective monthly" value={money(result.effective_monthly)} hint="upfront spread over each term" />
            )}
          </dl>

          {result.items.length > 1 && (
            <ul className="space-y-1 border-t border-line pt-3 text-sm">
              {result.items.map((it, i) => (
                <li key={i} className="flex justify-between gap-2">
                  <span className="truncate text-slate-600">{it.name}</span>
                  <span className={`tabular-nums ${it.error ? 'text-red-600' : ''}`}>{it.error ? 'unavailable' : money(it.monthly)}</span>
                </li>
              ))}
            </ul>
          )}

          <details className="border-t border-line pt-3 text-xs text-slate-500">
            <summary className="cursor-pointer font-medium text-slate-600">Assumptions &amp; price list</summary>
            <ul className="mt-2 list-disc space-y-1 pl-4">
              {result.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
            {Object.keys(result.price_list_dates).length > 0 && (
              <p className="mt-2">
                AWS price list dated:{' '}
                {Object.entries(result.price_list_dates)
                  .map(([k, v]) => `${k} (${v})`)
                  .join(', ')}
              </p>
            )}
          </details>
        </>
      )}
    </aside>
  )
}

function Row({ label, value, big, hint }: { label: string; value: string; big?: boolean; hint?: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">
        {label}
        {hint && <span className="ml-1 text-slate-400">({hint})</span>}
      </dt>
      <dd className={`tabular-nums ${big ? 'text-3xl font-bold text-navy' : 'text-lg font-semibold'}`}>{value}</dd>
    </div>
  )
}
