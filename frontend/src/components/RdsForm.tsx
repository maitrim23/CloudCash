import { api } from '../api'
import { useCached } from '../hooks'
import type { RdsItem } from '../types'
import { Field, NumberInput, Select, Combo } from './controls'
import { PurchaseFields } from './PurchaseFields'

const comboKey = (e: { engine: string; edition: string; license_model: string }) => [e.engine, e.edition, e.license_model].join('|')
const comboLabel = (e: { engine: string; edition: string; license_model: string }) =>
  [e.engine, e.edition, e.license_model !== 'No license required' ? e.license_model : ''].filter(Boolean).join(' · ')

export function RdsForm({ item, onChange, regions }: { item: RdsItem; onChange: (i: RdsItem) => void; regions: string[] }) {
  const { data: catalog, error } = useCached(`rds:${item.region}`, () => api.rdsCatalog(item.region))
  const set = (patch: Partial<RdsItem>) => onChange({ ...item, ...patch })
  const current = comboKey({ engine: item.engine, edition: item.edition, license_model: item.license_model })
  const spec = catalog?.instances.find((i) => i.instance_type === item.instance_type)
  const available = (catalog?.instances ?? []).filter((i) => i.combos.includes(current))
  const provisioned = item.storage_type === 'io1' || item.storage_type === 'io2'

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Field label="Region">
          <Select aria-label="Region" value={item.region} onChange={(region) => set({ region })} options={regions.map((r) => ({ value: r, label: r }))} />
        </Field>
        <Field label="Database engine" className="md:col-span-2">
          <select
            aria-label="Database engine"
            className="w-full rounded-md border border-line bg-white px-2.5 py-1.5 text-sm shadow-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
            value={current}
            onChange={(e) => {
              const [engine, edition, license_model] = e.target.value.split('|')
              set({ engine, edition, license_model })
            }}
          >
            {(catalog?.engines ?? [{ engine: item.engine, edition: item.edition, license_model: item.license_model }]).map((e) => (
              <option key={comboKey(e)} value={comboKey(e)}>
                {comboLabel(e)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Deployment">
          <Select
            aria-label="Deployment"
            value={item.deployment}
            onChange={(deployment) => set({ deployment })}
            options={[
              { value: 'single_az', label: 'Single-AZ' },
              { value: 'multi_az', label: 'Multi-AZ (standby)' },
            ]}
          />
        </Field>
        <Field
          label="Instance class"
          hint={spec ? `${spec.vcpu} vCPU · ${spec.memory}` : error ? error : catalog ? 'Not available for this engine here' : 'Loading…'}
        >
          <Combo value={item.instance_type} onChange={(instance_type) => set({ instance_type })} options={available.map((i) => ({ value: i.instance_type, label: `${i.vcpu} vCPU · ${i.memory}` }))} />
        </Field>
        <Field label="Number of instances">
          <NumberInput aria-label="Number of instances" value={item.quantity} min={1} step={1} onChange={(v) => set({ quantity: v ?? 1 })} />
        </Field>
        <Field label="Storage type">
          <Select
            aria-label="Storage type"
            value={item.storage_type}
            onChange={(storage_type) => set({ storage_type })}
            options={[
              { value: 'gp3', label: 'General Purpose SSD (gp3)' },
              { value: 'gp2', label: 'General Purpose SSD (gp2)' },
              { value: 'io1', label: 'Provisioned IOPS (io1)' },
              { value: 'io2', label: 'Provisioned IOPS (io2)' },
            ]}
          />
        </Field>
        <Field label="Storage (GB)">
          <NumberInput aria-label="Storage in GB" value={item.storage_gb} min={1} onChange={(v) => set({ storage_gb: v ?? 1 })} />
        </Field>
        {provisioned && (
          <Field label="Provisioned IOPS">
            <NumberInput aria-label="Provisioned IOPS" nullable value={item.iops} min={0} placeholder="1000" onChange={(v) => set({ iops: v })} />
          </Field>
        )}
      </div>
      <PurchaseFields pricing={item.pricing} usage={item.usage} onPricing={(pricing) => set({ pricing })} onUsage={(usage) => set({ usage })} allowConvertible={false} />
    </div>
  )
}
