import { useEffect, useState } from 'react'
import { api } from '../api'
import { newVolume } from '../defaults'
import { useCached } from '../hooks'
import { money } from '../format'
import type { Alternatives, EbsVolume, Ec2Item } from '../types'
import { Button, Combo, Field, NumberInput, Select } from './controls'
import { PurchaseFields } from './PurchaseFields'

const VOLUME_TYPES = [
  { value: 'gp3', label: 'General Purpose SSD (gp3)' },
  { value: 'gp2', label: 'General Purpose SSD (gp2)' },
  { value: 'io1', label: 'Provisioned IOPS SSD (io1)' },
  { value: 'io2', label: 'Provisioned IOPS SSD (io2)' },
  { value: 'st1', label: 'Throughput Optimized HDD (st1)' },
  { value: 'sc1', label: 'Cold HDD (sc1)' },
] as const

export function Ec2Form({ item, onChange, regions }: { item: Ec2Item; onChange: (i: Ec2Item) => void; regions: string[] }) {
  const { data: catalog, error } = useCached(`ec2:${item.region}`, () => api.ec2Catalog(item.region))
  const spec = catalog?.instances.find((i) => i.instance_type === item.instance_type)
  const set = (patch: Partial<Ec2Item>) => onChange({ ...item, ...patch })
  const setVol = (idx: number, patch: Partial<EbsVolume>) =>
    set({ ebs: item.ebs.map((v, i) => (i === idx ? { ...v, ...patch } : v)) })

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Field label="Region">
          <Select aria-label="Region" value={item.region} onChange={(region) => set({ region })} options={regions.map((r) => ({ value: r, label: r }))} />
        </Field>
        <Field label="Instance type" hint={spec ? `${spec.vcpu} vCPU · ${spec.memory}` : error ? error : catalog ? 'Not available in this region' : 'Loading…'}>
          <Combo
            value={item.instance_type}
            onChange={(instance_type) => {
              const next = catalog?.instances.find((i) => i.instance_type === instance_type)
              set({ instance_type, os: next && !next.os.includes(item.os) ? next.os[0] : item.os })
            }}
            options={(catalog?.instances ?? []).map((i) => ({ value: i.instance_type, label: `${i.vcpu} vCPU · ${i.memory}` }))}
          />
        </Field>
        <Field label="Operating system">
          <Select
            aria-label="Operating system"
            value={item.os}
            onChange={(os) => set({ os })}
            options={(spec?.os ?? [item.os]).map((o) => ({ value: o, label: o }))}
          />
        </Field>
        <Field label="Number of instances">
          <NumberInput aria-label="Number of instances" value={item.quantity} min={1} step={1} onChange={(v) => set({ quantity: v ?? 1 })} />
        </Field>
      </div>

      <PurchaseFields
        pricing={item.pricing}
        usage={item.usage}
        onPricing={(pricing) => set({ pricing })}
        onUsage={(usage) => set({ usage })}
        allowConvertible
        allowSavingsPlan
      />

      <AlternativesPanel item={item} onPick={(instance_type) => set({ instance_type })} />

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-slate-700">EBS volumes (per instance)</h4>
          <Button onClick={() => set({ ebs: [...item.ebs, newVolume()] })}>+ Add volume</Button>
        </div>
        {item.ebs.length === 0 && <p className="text-xs text-slate-500">No storage attached.</p>}
        {item.ebs.map((v, idx) => (
          <div key={idx} className="rounded-md border border-line bg-slate-50 p-3">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Field label="Volume type">
                <Select aria-label="Volume type" value={v.volume_type} onChange={(volume_type) => setVol(idx, { volume_type })} options={[...VOLUME_TYPES]} />
              </Field>
              <Field label="Size (GB)">
                <NumberInput aria-label="Size in GB" value={v.size_gb} min={1} onChange={(n) => setVol(idx, { size_gb: n ?? 1 })} />
              </Field>
              {(v.volume_type === 'gp3' || v.volume_type === 'io1' || v.volume_type === 'io2') && (
                <Field label="IOPS" hint={v.volume_type === 'gp3' ? '3000 included' : 'provisioned'}>
                  <NumberInput aria-label="IOPS" nullable value={v.iops} min={0} onChange={(n) => setVol(idx, { iops: n })} placeholder={v.volume_type === 'gp3' ? '3000' : '3000'} />
                </Field>
              )}
              {v.volume_type === 'gp3' && (
                <Field label="Throughput (MB/s)" hint="125 included">
                  <NumberInput aria-label="Throughput" nullable value={v.throughput_mbps} min={0} onChange={(n) => setVol(idx, { throughput_mbps: n })} placeholder="125" />
                </Field>
              )}
              <Field label="Snapshots / month">
                <NumberInput aria-label="Snapshots per month" value={v.snapshots_per_month} min={0} step={1} onChange={(n) => setVol(idx, { snapshots_per_month: n ?? 0 })} />
              </Field>
              {v.snapshots_per_month > 0 && (
                <Field label="Changed per snapshot (GB)">
                  <NumberInput aria-label="Changed GB per snapshot" value={v.snapshot_changed_gb} min={0} onChange={(n) => setVol(idx, { snapshot_changed_gb: n ?? 0 })} />
                </Field>
              )}
              <div className="flex items-end">
                <Button variant="danger" onClick={() => set({ ebs: item.ebs.filter((_, i) => i !== idx) })}>
                  Remove
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** "Same specs for less" hints. Loads only when asked, so it never slows typing. */
function AlternativesPanel({ item, onPick }: { item: Ec2Item; onPick: (instanceType: string) => void }) {
  const [data, setData] = useState<Alternatives | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const stamp = `${item.region}|${item.instance_type}|${item.os}`

  useEffect(() => {
    // The suggestions belong to one exact instance; forget them when it changes.
    setData(null)
    setError(null)
  }, [stamp])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setData(await api.alternatives(item.region, item.instance_type, item.os))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-md border border-dashed border-line p-3 text-sm">
      <Button onClick={load} disabled={loading}>
        {loading ? 'Looking…' : 'Find cheaper alternatives'}
      </Button>
      {error && <span className="ml-3 text-xs text-slate-500">{error}</span>}
      {data && (
        <div className="mt-3">
          {data.alternatives.length === 0 ? (
            <p className="text-xs text-slate-500">No cheaper current-generation instance has at least the same vCPU and memory.</p>
          ) : (
            <>
              <p className="mb-2 text-xs text-slate-500">
                At least the same vCPU and memory, lower On-Demand price than {data.instance_type} ({money(Number(data.hourly) * 730)}/month). Check CPU architecture and your software before switching.
              </p>
              <ul className="space-y-1">
                {data.alternatives.map((a) => (
                  <li key={a.instance_type} className="flex flex-wrap items-center gap-3 text-xs">
                    <span className="w-28 font-mono font-semibold">{a.instance_type}</span>
                    <span className="text-slate-500">
                      {a.vcpu} vCPU · {a.memory_gib} GiB
                    </span>
                    <span className="tabular-nums">{money(Number(a.hourly) * 730)}/mo</span>
                    <span className="font-semibold text-emerald-700">−{a.saving_pct}%</span>
                    {a.arm && <span className="rounded bg-amber-100 px-1.5 text-amber-800">Arm (Graviton)</span>}
                    <Button className="!px-2 !py-0.5 text-xs" onClick={() => onPick(a.instance_type)}>
                      Use
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  )
}
