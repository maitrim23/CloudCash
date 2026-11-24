import { useState } from 'react'
import { money } from '../format'
import type { ItemResult, LineItem } from '../types'
import { Button, inputCls } from './controls'
import { Ec2Form } from './Ec2Form'
import { RdsForm } from './RdsForm'
import { DtForm } from './DtForm'
import { S3Form } from './S3Form'

const BADGE: Record<LineItem['type'], { label: string; cls: string }> = {
  ec2: { label: 'EC2', cls: 'bg-orange-100 text-orange-800' },
  s3: { label: 'S3', cls: 'bg-emerald-100 text-emerald-800' },
  rds: { label: 'RDS', cls: 'bg-sky-100 text-sky-800' },
  dt: { label: 'Transfer', cls: 'bg-violet-100 text-violet-800' },
}

export function ItemCard({
  item,
  result,
  regions,
  onChange,
  onRemove,
  onDuplicate,
}: {
  item: LineItem
  result?: ItemResult
  regions: string[]
  onChange: (i: LineItem) => void
  onRemove: () => void
  onDuplicate: () => void
}) {
  const [showMath, setShowMath] = useState(false)
  const badge = BADGE[item.type]

  return (
    <section className="rounded-xl border border-line bg-white shadow-sm">
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <span className={`rounded px-2 py-0.5 text-xs font-bold ${badge.cls}`}>{badge.label}</span>
        <input
          aria-label="Item name"
          className={`${inputCls} max-w-xs font-semibold`}
          value={item.name}
          onChange={(e) => onChange({ ...item, name: e.target.value })}
        />
        <div className="ml-auto flex items-center gap-2">
          <Button onClick={onDuplicate}>Duplicate</Button>
          <Button variant="danger" onClick={onRemove}>
            Remove
          </Button>
        </div>
      </header>

      <div className="p-4">
        {item.type === 'ec2' && <Ec2Form item={item} regions={regions} onChange={onChange} />}
        {item.type === 's3' && <S3Form item={item} regions={regions} onChange={onChange} />}
        {item.type === 'rds' && <RdsForm item={item} regions={regions} onChange={onChange} />}
        {item.type === 'dt' && <DtForm item={item} regions={regions} onChange={onChange} />}
      </div>

      {result && (
        <footer className="border-t border-line bg-slate-50 px-4 py-3">
          {result.error ? (
            <p role="alert" className="text-sm font-medium text-red-700">
              {result.error}
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-xs text-slate-500">{result.summary}</p>
                <p className="text-sm">
                  <span className="font-semibold">{money(result.monthly)}</span> / month
                  {Number(result.upfront) > 0 && <span className="text-slate-500"> + {money(result.upfront)} upfront</span>}
                </p>
              </div>
              <button type="button" className="mt-2 text-xs font-medium text-accent-dark hover:underline" onClick={() => setShowMath((s) => !s)}>
                {showMath ? 'Hide calculation' : 'Show calculation'}
              </button>
              {showMath && (
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="text-slate-500">
                      <tr>
                        <th className="py-1 pr-3 font-medium">Line</th>
                        <th className="py-1 pr-3 text-right font-medium">Monthly</th>
                        <th className="py-1 text-right font-medium">Upfront</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.components.map((c) => (
                        <tr key={c.label} className="border-t border-line align-top">
                          <td className="py-1.5 pr-3">
                            <div className="font-medium text-slate-700">{c.label}</div>
                            {c.explain.map((line, i) => (
                              <div key={i} className="font-mono text-[11px] text-slate-500">
                                {line}
                              </div>
                            ))}
                          </td>
                          <td className="py-1.5 pr-3 text-right tabular-nums">{money(c.monthly)}</td>
                          <td className="py-1.5 text-right tabular-nums">{Number(c.upfront) > 0 ? money(c.upfront) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {result.warnings.map((w) => (
                    <p key={w} className="mt-1 text-[11px] text-amber-700">
                      ⚠ {w}
                    </p>
                  ))}
                </div>
              )}
            </>
          )}
        </footer>
      )}
    </section>
  )
}
