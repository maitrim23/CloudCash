import { useEffect, useId, useState, type ReactNode } from 'react'

export const inputCls =
  'w-full rounded-md border border-line bg-white px-2.5 py-1.5 text-sm text-ink shadow-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/30'

export function Field({ label, hint, children, className = '' }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`flex flex-col gap-1 text-xs font-medium text-slate-600 ${className}`}>
      <span>{label}</span>
      {children}
      {hint && <span className="font-normal text-slate-400">{hint}</span>}
    </label>
  )
}

/** Number input that tolerates half-typed values ("1.", "") without fighting the user. */
export function NumberInput({
  value,
  onChange,
  min,
  max,
  step,
  nullable = false,
  placeholder,
  'aria-label': ariaLabel,
}: {
  value: number | null
  onChange: (v: number | null) => void
  min?: number
  max?: number
  step?: number
  nullable?: boolean
  placeholder?: string
  'aria-label'?: string
}) {
  const [text, setText] = useState(value === null ? '' : String(value))
  useEffect(() => {
    // Re-sync only when the outside value genuinely differs from what the text means.
    const parsed = text === '' ? null : Number(text)
    if (parsed !== value) setText(value === null ? '' : String(value))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  return (
    <input
      className={inputCls}
      type="number"
      inputMode="decimal"
      aria-label={ariaLabel}
      min={min}
      max={max}
      step={step ?? 'any'}
      placeholder={placeholder}
      value={text}
      onChange={(e) => {
        const t = e.target.value
        setText(t)
        if (t === '') return onChange(nullable ? null : 0)
        const n = Number(t)
        if (Number.isFinite(n)) onChange(n)
      }}
    />
  )
}

export function Select<T extends string>({
  value,
  onChange,
  options,
  'aria-label': ariaLabel,
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
  'aria-label'?: string
}) {
  return (
    <select className={inputCls} aria-label={ariaLabel} value={value} onChange={(e) => onChange(e.target.value as T)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

/** Free-text input with a searchable dropdown of suggestions (native <datalist>). */
export function Combo({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label?: string }[]
  placeholder?: string
}) {
  const id = useId()
  return (
    <>
      <input className={inputCls} list={id} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      <datalist id={id}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </datalist>
    </>
  )
}

export function Button({
  children,
  variant = 'ghost',
  ...rest
}: { variant?: 'primary' | 'ghost' | 'danger' } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const styles = {
    primary: 'bg-accent text-navy hover:bg-amber-400 font-semibold',
    ghost: 'border border-line bg-white text-slate-700 hover:bg-slate-50',
    danger: 'border border-red-200 bg-white text-red-700 hover:bg-red-50',
  }[variant]
  return (
    <button
      type="button"
      {...rest}
      className={`rounded-md px-3 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${rest.className ?? ''}`}
    >
      {children}
    </button>
  )
}
