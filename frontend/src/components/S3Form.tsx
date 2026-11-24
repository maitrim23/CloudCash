import { api } from '../api'
import { useCached } from '../hooks'
import type { S3Class, S3Item } from '../types'
import { Field, NumberInput, Select } from './controls'

export function S3Form({ item, onChange, regions }: { item: S3Item; onChange: (i: S3Item) => void; regions: string[] }) {
  const { data } = useCached('s3-catalog', api.s3Catalog)
  const set = (patch: Partial<S3Item>) => onChange({ ...item, ...patch })
  const classes = data?.storage_classes ?? [{ id: 'standard' as S3Class, label: 'S3 Standard' }]
  const hasRetrieval = item.storage_class !== 'standard'

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Field label="Region">
        <Select aria-label="Region" value={item.region} onChange={(region) => set({ region })} options={regions.map((r) => ({ value: r, label: r }))} />
      </Field>
      <Field label="Storage class">
        <Select
          aria-label="Storage class"
          value={item.storage_class}
          onChange={(storage_class) => set({ storage_class, retrieval_gb: storage_class === 'standard' ? 0 : item.retrieval_gb })}
          options={classes.map((c) => ({ value: c.id, label: c.label }))}
        />
      </Field>
      <Field label="Storage (GB / month)" hint="1 TB = 1024 GB, as in AWS tiers">
        <NumberInput aria-label="Storage in GB" value={item.storage_gb} min={0} onChange={(v) => set({ storage_gb: v ?? 0 })} />
      </Field>
      <Field label="PUT/COPY/POST/LIST requests">
        <NumberInput aria-label="PUT requests" value={item.put_requests} min={0} onChange={(v) => set({ put_requests: v ?? 0 })} />
      </Field>
      <Field label="GET/SELECT requests">
        <NumberInput aria-label="GET requests" value={item.get_requests} min={0} onChange={(v) => set({ get_requests: v ?? 0 })} />
      </Field>
      {hasRetrieval && (
        <Field label="Data retrieval (GB)">
          <NumberInput aria-label="Retrieval in GB" value={item.retrieval_gb} min={0} onChange={(v) => set({ retrieval_gb: v ?? 0 })} />
        </Field>
      )}
    </div>
  )
}
