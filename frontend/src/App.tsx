import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { ComparePanel } from './components/ComparePanel'
import { Button, inputCls } from './components/controls'
import { ItemCard } from './components/ItemCard'
import { SavedPanel } from './components/SavedPanel'
import { Summary } from './components/Summary'
import { newDt, newEc2, newRds, newS3 } from './defaults'
import { regionLabel } from './format'
import { useEstimate, useMeta } from './hooks'
import type { LineItem, SavedScenario, Scenario } from './types'

type Tab = 'estimate' | 'compare' | 'saved'
type Draft = { uid: number; item: LineItem }

let nextUid = 1
const toDrafts = (items: LineItem[]): Draft[] => items.map((item) => ({ uid: nextUid++, item }))

export default function App() {
  const { meta, error: metaError } = useMeta()
  const regions = useMemo(() => meta?.regions.map((r) => r.region) ?? [], [meta])
  const [tab, setTab] = useState<Tab>('estimate')

  const [name, setName] = useState('My estimate')
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [saved, setSaved] = useState<SavedScenario[]>([])
  const [status, setStatus] = useState<string | null>(null)

  const scenario: Scenario = useMemo(() => ({ name: name.trim() || 'Untitled', items: drafts.map((d) => d.item) }), [name, drafts])
  const { result, error, loading } = useEstimate(scenario)

  const refreshSaved = useCallback(() => api.listSaved().then(setSaved).catch(() => setSaved([])), [])
  useEffect(() => {
    refreshSaved()
  }, [refreshSaved])

  const defaultRegion = regions.includes('ap-south-1') ? 'ap-south-1' : (regions[0] ?? 'us-east-1')
  const add = (make: (region: string) => LineItem) => setDrafts((d) => [...d, ...toDrafts([make(defaultRegion)])])

  async function save() {
    setStatus(null)
    try {
      const s = activeId ? await api.updateSaved(activeId, scenario) : await api.createSaved(scenario)
      setActiveId(s.id)
      setStatus(`Saved “${s.name}”`)
      refreshSaved()
    } catch (e) {
      setStatus(`Could not save: ${(e as Error).message}`)
    }
  }

  function open(s: SavedScenario) {
    setName(s.scenario.name)
    setDrafts(toDrafts(s.scenario.items))
    setActiveId(s.id)
    setStatus(null)
    setTab('estimate')
  }

  function reset() {
    setName('My estimate')
    setDrafts([])
    setActiveId(null)
    setStatus(null)
  }

  async function remove(s: SavedScenario) {
    await api.deleteSaved(s.id)
    if (s.id === activeId) setActiveId(null)
    refreshSaved()
  }

  return (
    <div className="min-h-screen">
      <header className="bg-navy text-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <div>
            <h1 className="text-lg font-bold tracking-tight">
              Cost<span className="text-accent">Goblin</span>
            </h1>
            <p className="text-xs text-slate-300">AWS list-price estimates, built from the public price list</p>
          </div>
          <nav className="ml-auto flex gap-1" aria-label="Sections">
            {(
              [
                ['estimate', 'Estimate'],
                ['compare', 'Compare'],
                ['saved', `Saved (${saved.length})`],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                aria-current={tab === id ? 'page' : undefined}
                onClick={() => setTab(id)}
                className={`rounded-md px-3 py-1.5 text-sm ${tab === id ? 'bg-navy-2 text-accent' : 'text-slate-200 hover:bg-navy-2'}`}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {metaError && (
          <p role="alert" className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
            Could not reach the API ({metaError}). Is the backend running on port 8000?
          </p>
        )}
        {meta && regions.length === 0 && (
          <p role="alert" className="mb-4 rounded-md bg-amber-50 p-3 text-sm text-amber-800">
            The price database is empty. Run <code>python -m app.pricing.ingest --regions ap-south-1 --download</code> in the backend folder.
          </p>
        )}

        {tab === 'estimate' && (
          <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
            <div className="space-y-4">
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex flex-1 flex-col gap-1 text-xs font-medium text-slate-600">
                  Estimate name
                  <input aria-label="Estimate name" className={`${inputCls} max-w-md text-base font-semibold`} value={name} onChange={(e) => setName(e.target.value)} />
                </label>
                <Button variant="primary" onClick={save} disabled={drafts.length === 0}>
                  {activeId ? 'Save changes' : 'Save estimate'}
                </Button>
                <Button onClick={reset}>New</Button>
              </div>
              {status && (
                <p role="status" className="text-sm text-slate-600">
                  {status}
                </p>
              )}

              <div className="flex flex-wrap gap-2" role="group" aria-label="Add a service">
                <Button onClick={() => add(newEc2)} disabled={!regions.length}>
                  + EC2
                </Button>
                <Button onClick={() => add(newS3)} disabled={!regions.length}>
                  + S3
                </Button>
                <Button onClick={() => add(newRds)} disabled={!regions.length}>
                  + RDS
                </Button>
                <Button onClick={() => add(newDt)} disabled={!regions.length}>
                  + Data transfer
                </Button>
                <span className="self-center text-xs text-slate-500">
                  Regions loaded: {regions.length ? regions.map(regionLabel).join(', ') : 'none'}
                </span>
              </div>

              {drafts.length === 0 && (
                <p className="rounded-xl border border-dashed border-line bg-white p-10 text-center text-sm text-slate-500">
                  Your estimate is empty. Add EC2, S3 or RDS above to start pricing.
                </p>
              )}

              {drafts.map((d, idx) => (
                <ItemCard
                  key={d.uid}
                  item={d.item}
                  result={result?.items[idx]}
                  regions={regions}
                  onChange={(item) => setDrafts((all) => all.map((x) => (x.uid === d.uid ? { ...x, item } : x)))}
                  onRemove={() => setDrafts((all) => all.filter((x) => x.uid !== d.uid))}
                  onDuplicate={() =>
                    setDrafts((all) => {
                      const at = all.findIndex((x) => x.uid === d.uid)
                      const copy = toDrafts([structuredClone({ ...d.item, name: `${d.item.name} (copy)` })])
                      return [...all.slice(0, at + 1), ...copy, ...all.slice(at + 1)]
                    })
                  }
                />
              ))}
            </div>
            <Summary result={result} loading={loading} error={error} />
          </div>
        )}

        {tab === 'compare' && <ComparePanel current={scenario} saved={saved} />}
        {tab === 'saved' && <SavedPanel saved={saved} activeId={activeId} onOpen={open} onDelete={remove} />}
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-slate-500">
        Estimates use public AWS list prices (no discounts, taxes or Free Tier) and are not a bill. This is an independent learning project and is not affiliated with, endorsed by or sponsored by
        Amazon Web Services.
      </footer>
    </div>
  )
}
