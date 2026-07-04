import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { ws } from '../lib/ws'
import type { TfData } from '../lib/sensorTypes'

/** Low-rate (2Hz) table, plain React state is fine here — no canvas needed. */
export function TfHealthTable() {
  const [tf, setTf] = useState<TfData | null>(null)
  useEffect(() => ws.on('tf', (data) => setTf(data as TfData)), [])

  if (!tf) return <p className="text-xs text-ink-dim">waiting for /tf…</p>

  return (
    <div className="space-y-1.5">
      {Object.entries(tf).map(([pair, frame]) => (
        <div key={pair} className="flex items-center justify-between text-xs">
          <span className="flex items-center gap-1.5 font-mono text-ink-dim">
            <span className={clsx('h-1.5 w-1.5 rounded-full', frame.ok ? 'bg-good' : 'bg-ink-dim/40')} />
            {pair}
          </span>
          <span className={clsx(frame.ok ? 'text-ink' : 'text-ink-dim/60')}>
            {!frame.ok ? 'absent' : frame.age == null ? 'static' : `${frame.age.toFixed(1)}s ago`}
          </span>
        </div>
      ))}
      <p className="pt-1 text-[10px] text-ink-dim/70">
        map→odom only appears once SLAM/localization is running — its absence is normal.
      </p>
    </div>
  )
}
