import { api } from '../api'
import { useCached } from '../hooks'
import type { DataTransferItem } from '../types'
import { Field, NumberInput, Select } from './controls'

export function DtForm({ item, onChange, regions }: { item: DataTransferItem; onChange: (i: DataTransferItem) => void; regions: string[] }) {
  const { data: catalog, error } = useCached(`dt:${item.region}`, () => api.dtCatalog(item.region))
  const set = (patch: Partial<DataTransferItem>) => onChange({ ...item, ...patch })
  const dests = catalog?.destinations ?? []

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Field label="Data leaves region">
          <Select aria-label="Region" value={item.region} onChange={(region) => set({ region, destination_region: null })} options={regions.map((r) => ({ value: r, label: r }))} />
        </Field>
        <Field label="Out to the internet (GB / month)">
          <NumberInput aria-label="Internet out GB" value={item.internet_out_gb} min={0} onChange={(v) => set({ internet_out_gb: v ?? 0 })} />
        </Field>
        <Field label="To another AWS region (GB / month)">
          <NumberInput aria-label="Inter-region GB" value={item.inter_region_gb} min={0} onChange={(v) => set({ inter_region_gb: v ?? 0 })} />
        </Field>
        <Field label="Destination region" hint={error ?? undefined}>
          <select
            aria-label="Destination region"
            disabled={item.inter_region_gb <= 0}
            className="w-full rounded-md border border-line bg-white px-2.5 py-1.5 text-sm shadow-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/30 disabled:bg-slate-100"
            value={item.destination_region ?? ''}
            onChange={(e) => set({ destination_region: e.target.value || null })}
          >
            <option value="">Select…</option>
            {dests.map((d) => (
              <option key={d.region} value={d.region}>
                {d.name} · {d.region}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Between availability zones (GB / month)" hint="billed in each direction">
          <NumberInput aria-label="Cross-AZ GB" value={item.cross_az_gb} min={0} onChange={(v) => set({ cross_az_gb: v ?? 0 })} />
        </Field>
        <label className="flex items-end gap-2 pb-1.5 text-xs font-medium text-slate-600">
          <input type="checkbox" checked={item.apply_free_tier} onChange={(e) => set({ apply_free_tier: e.target.checked })} />
          Apply the free 100 GB / month
        </label>
      </div>
      <p className="text-xs text-slate-500">Data transferred into AWS is free. The free 100 GB is given once per AWS account.</p>
    </div>
  )
}
