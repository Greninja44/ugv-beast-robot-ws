import type { ReactNode } from 'react'
import clsx from 'clsx'

export function GlassCard({ title, children, className }: {
  title?: string; children: ReactNode; className?: string
}) {
  return (
    <section className={clsx('glass p-4', className)}>
      {title && (
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-ink-dim">
          {title}
        </h2>
      )}
      {children}
    </section>
  )
}

export function Stat({ label, value, unit, tone = 'default' }: {
  label: string; value: string | number | null | undefined; unit?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
}) {
  const toneCls = { default: 'text-ink', good: 'text-good', warn: 'text-warn', bad: 'text-bad' }[tone]
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-ink-dim">{label}</div>
      <div className={clsx('font-mono text-xl leading-tight', toneCls)}>
        {value ?? '—'}
        {unit && value != null && <span className="ml-1 text-xs text-ink-dim">{unit}</span>}
      </div>
    </div>
  )
}
