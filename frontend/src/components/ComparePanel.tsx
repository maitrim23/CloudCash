import { useState } from 'react'
import { api } from '../api'
import { money, signedMoney, signedPercent } from '../format'
import type { CompareResult, SavedScenario, Scenario } from '../types'
import { Button } from './controls'

type Option = { key: string; label: string; scenario: Scenario }

export function ComparePanel({ current, saved }: { current: Scenario; saved: SavedScenario[] }) {
  const options: Option[] = [
    ...(current.items.length ? [{ key: 'current', label: `${current.name} (editing)`, scenario: current }] : []),
    ...saved.map((s) => ({ key: s.id, label: s.name, scenario: s.scenario })),
  ]
  const [picked, setPicked] = useState<string[]>([])
  const [result, setResult] = useState<CompareResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const toggle = (key: string) => setPicked((p) => (p.includes(key) ? p.filter((k) => k !== key) : p.length < 4 ? [...p, key] : p))

  async function run() {
    setBusy(true)
    setError(null)
    try {
      // Names must be unique for the table; suffix duplicates.
      const chosen = picked.map((k) => options.find((o) => o.key === k)!.scenario)
      const seen = new Map<string, number>()
      const scenarios = chosen.map((s) => {
        const n = (seen.get(s.name) ?? 0) + 1
        seen.set(s.name, n)
        return n > 1 ? { ...s, name: `${s.name} (${n})` } : s
      })
      setResult(await api.compare(scenarios))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const max = result ? Math.max(...result.diffs.map((d) => Number(d.effective_monthly)), 1) : 1

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-line bg-white p-4 shadow-sm">
        <h2 className="text-base font-semibold">Pick 2–4 scenarios</h2>
        <p className="mb-3 text-sm text-slate-500">The first one you pick is the baseline. Save scenarios from the Estimate tab to compare them here.</p>
        {options.length < 2 && <p className="text-sm text-amber-700">You need at least two scenarios (the one you are editing counts).</p>}
        <ul className="space-y-2">
          {options.map((o) => (
            <li key={o.key}>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input type="checkbox" checked={picked.includes(o.key)} onChange={() => toggle(o.key)} />
                <span>{o.label}</span>
                <span className="text-xs text-slate-400">{o.scenario.items.length} item(s)</span>
                {picked.includes(o.key) && <span className="rounded bg-slate-100 px-1.5 text-xs">{picked.indexOf(o.key) === 0 ? 'baseline' : `#${picked.indexOf(o.key) + 1}`}</span>}
              </label>
            </li>
          ))}
        </ul>
        <div className="mt-4">
          <Button variant="primary" disabled={picked.length < 2 || busy} onClick={run}>
            {busy ? 'Comparing…' : 'Compare'}
          </Button>
        </div>
        {error && (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {error}
          </p>
        )}
      </section>

      {result && (
        <section className="rounded-xl border border-line bg-white p-4 shadow-sm">
          <h2 className="mb-1 text-base font-semibold">Result</h2>
          <p className="mb-4 text-sm text-slate-500">
            Ranked on <b>effective monthly cost</b> (upfront fees spread over their term) so Reserved and On-Demand are compared fairly. Cheapest: <b>{result.cheapest}</b>.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-2 pr-3 font-medium">Scenario</th>
                  <th className="py-2 pr-3 text-right font-medium">Monthly</th>
                  <th className="py-2 pr-3 text-right font-medium">Upfront</th>
                  <th className="py-2 pr-3 text-right font-medium">First 12 months</th>
                  <th className="py-2 pr-3 text-right font-medium">Effective / month</th>
                  <th className="py-2 text-right font-medium">vs baseline</th>
                </tr>
              </thead>
              <tbody>
                {result.diffs.map((d, i) => {
                  const est = result.scenarios[i]
                  const delta = Number(d.vs_baseline)
                  return (
                    <tr key={d.name} className="border-t border-line">
                      <td className="py-2 pr-3 font-medium">
                        {d.name} {d.name === result.cheapest && <span className="ml-1 rounded bg-emerald-100 px-1.5 text-xs text-emerald-800">cheapest</span>}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">{money(d.monthly)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{money(est.upfront)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{money(d.first_12_months)}</td>
                      <td className="py-2 pr-3 text-right font-semibold tabular-nums">{money(d.effective_monthly)}</td>
                      <td className={`py-2 text-right tabular-nums ${delta < 0 ? 'text-emerald-700' : delta > 0 ? 'text-red-700' : 'text-slate-500'}`}>
                        {i === 0 ? 'baseline' : `${signedMoney(d.vs_baseline)} (${signedPercent(d.vs_baseline_pct)})`}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-6 space-y-2" aria-label="Effective monthly cost bars">
            {result.diffs.map((d) => (
              <div key={d.name} className="flex items-center gap-3 text-xs">
                <span className="w-32 shrink-0 truncate text-slate-600">{d.name}</span>
                <div className="h-5 flex-1 rounded bg-slate-100">
                  <div className="h-5 rounded bg-accent" style={{ width: `${(Number(d.effective_monthly) / max) * 100}%` }} />
                </div>
                <span className="w-24 text-right tabular-nums">{money(d.effective_monthly)}</span>
              </div>
            ))}
          </div>

          {result.scenarios.some((s) => s.items.some((i) => i.error)) && (
            <p className="mt-4 text-xs text-amber-700">⚠ Some line items could not be priced and are excluded from totals. Open the scenario to see which.</p>
          )}
        </section>
      )}
    </div>
  )
}
