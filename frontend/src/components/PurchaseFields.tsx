import type { Pricing, Usage } from '../types'
import { Field, NumberInput, Select } from './controls'

/** Purchase option + utilisation. Shared by EC2 and RDS. */
export function PurchaseFields({
  pricing,
  usage,
  onPricing,
  onUsage,
  allowConvertible,
  allowSavingsPlan = false,
}: {
  pricing: Pricing
  usage: Usage
  onPricing: (p: Pricing) => void
  onUsage: (u: Usage) => void
  allowConvertible: boolean
  allowSavingsPlan?: boolean
}) {
  const committed = pricing.model !== 'on_demand'
  const models = [
    { value: 'on_demand' as const, label: 'On-Demand' },
    { value: 'reserved' as const, label: 'Reserved Instance' },
    ...(allowSavingsPlan ? [{ value: 'savings_plan' as const, label: 'Savings Plan' }] : []),
  ]
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Field label="Pricing model">
        <Select aria-label="Pricing model" value={pricing.model} onChange={(model) => onPricing({ ...pricing, model })} options={models} />
      </Field>

      {committed ? (
        <>
          {pricing.model === 'reserved' && allowConvertible && (
            <Field label="Offering class">
              <Select
                aria-label="Offering class"
                value={pricing.offering_class}
                onChange={(offering_class) => onPricing({ ...pricing, offering_class })}
                options={[
                  { value: 'standard', label: 'Standard' },
                  { value: 'convertible', label: 'Convertible' },
                ]}
              />
            </Field>
          )}
          {pricing.model === 'savings_plan' && (
            <Field label="Plan type">
              <Select
                aria-label="Plan type"
                value={pricing.sp_type}
                onChange={(sp_type) => onPricing({ ...pricing, sp_type })}
                options={[
                  { value: 'compute', label: 'Compute Savings Plan' },
                  { value: 'ec2_instance', label: 'EC2 Instance Savings Plan' },
                ]}
              />
            </Field>
          )}
          <Field label="Term">
            <Select
              aria-label="Term"
              value={pricing.term}
              onChange={(term) => onPricing({ ...pricing, term })}
              options={[
                { value: '1yr', label: '1 year' },
                { value: '3yr', label: '3 years' },
              ]}
            />
          </Field>
          <Field label="Payment option">
            <Select
              aria-label="Payment option"
              value={pricing.payment}
              onChange={(payment) => onPricing({ ...pricing, payment })}
              options={[
                { value: 'no_upfront', label: 'No upfront' },
                { value: 'partial_upfront', label: 'Partial upfront' },
                { value: 'all_upfront', label: 'All upfront' },
              ]}
            />
          </Field>
          <p className="col-span-full text-xs text-slate-500">
            Committed capacity is billed every hour (730 h/month), so utilisation does not apply.
            {pricing.model === 'savings_plan' && ' Partial upfront assumes 50% is paid at purchase.'}
          </p>
        </>
      ) : (
        <>
          <Field label="Utilisation">
            <Select
              aria-label="Utilisation"
              value={usage.mode}
              onChange={(mode) => onUsage({ ...usage, mode })}
              options={[
                { value: 'always', label: 'Always on (730 h)' },
                { value: 'percent_month', label: '% of the month' },
                { value: 'hours_per_day', label: 'Hours per day / week' },
              ]}
            />
          </Field>
          {usage.mode === 'percent_month' && (
            <Field label="% of month">
              <NumberInput aria-label="Percent of month" value={usage.percent} min={0} max={100} onChange={(v) => onUsage({ ...usage, percent: v ?? 0 })} />
            </Field>
          )}
          {usage.mode === 'hours_per_day' && (
            <>
              <Field label="Hours per day">
                <NumberInput aria-label="Hours per day" value={usage.hours_per_day} min={0} max={24} onChange={(v) => onUsage({ ...usage, hours_per_day: v ?? 0 })} />
              </Field>
              <Field label="Days per week">
                <NumberInput aria-label="Days per week" value={usage.days_per_week} min={0} max={7} onChange={(v) => onUsage({ ...usage, days_per_week: v ?? 0 })} />
              </Field>
            </>
          )}
        </>
      )}
    </div>
  )
}
