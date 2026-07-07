import { useEffect, useState } from 'react'
import { useRobot } from '../stores/robot'
import { useTeleop } from '../stores/teleop'
import { ws } from '../lib/ws'
import type { RobotMode } from '../lib/sensorTypes'
import { BatteryMedium, Wifi, WifiOff, Cpu, Thermometer, OctagonX, PlayCircle } from 'lucide-react'
import clsx from 'clsx'

const MODES: RobotMode[] = ['idle', 'teleop', 'explore', 'track', 'ai']
const AUTONOMOUS_MODES = new Set(['explore', 'track', 'ai'])

function ModePill({ authenticated }: { authenticated: boolean }) {
  const [mode, setMode] = useState<RobotMode | null>(null)
  useEffect(() => ws.on('mode', (data) => setMode(data as RobotMode)), [])

  const autonomous = mode != null && AUTONOMOUS_MODES.has(mode)
  return (
    <select
      value={mode ?? ''}
      onChange={(e) => ws.setMode(e.target.value)}
      disabled={!authenticated}
      title={authenticated ? 'Set /robot/mode — who currently holds motion authority'
        : 'Unlock control on the Manual Control page first'}
      className={clsx(
        'rounded-full border-0 px-2.5 py-1 text-xs font-medium appearance-none cursor-pointer',
        !authenticated && 'opacity-50 cursor-not-allowed',
        mode == null ? 'bg-white/5 text-ink-dim'
          : autonomous ? 'bg-good/10 text-good' : 'bg-white/5 text-ink-dim',
      )}
    >
      <option value="" disabled>MODE: …</option>
      {MODES.map((m) => (
        <option key={m} value={m}>MODE: {m}</option>
      ))}
    </select>
  )
}

function Pill({ ok, label }: { ok: boolean | null; label: string }) {
  return (
    <span className={clsx(
      'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
      ok == null ? 'bg-white/5 text-ink-dim'
        : ok ? 'bg-good/10 text-good' : 'bg-bad/10 text-bad',
    )}>
      <span className={clsx('h-1.5 w-1.5 rounded-full',
        ok == null ? 'bg-ink-dim' : ok ? 'bg-good animate-pulse' : 'bg-bad')} />
      {label}
    </span>
  )
}

export default function StatusStrip() {
  const { status, latencyMs, telemetry: t } = useRobot()
  const { authenticated, estopActive } = useTeleop()
  const online = status === 'online'

  return (
    <header className="flex items-center gap-3 px-4 py-2.5 border-b border-edge
                       bg-panel/60 backdrop-blur-md sticky top-0 z-10">
      <h1 className="text-sm font-semibold tracking-wide mr-1">UGV&nbsp;Beast</h1>

      <Pill ok={online} label={online ? 'LINK' : status.toUpperCase()} />
      <Pill ok={t ? t.ros : null} label="ROS" />
      <ModePill authenticated={authenticated} />

      <div className="ml-auto flex items-center gap-4 text-xs text-ink-dim">
        {t?.temp != null && (
          <span className="hidden sm:flex items-center gap-1">
            <Thermometer size={14} /> {t.temp.toFixed(0)}°C
          </span>
        )}
        {t && (
          <span className="hidden sm:flex items-center gap-1">
            <Cpu size={14} /> {t.cpu}%
          </span>
        )}
        <span className="flex items-center gap-1">
          {online ? <Wifi size={14} /> : <WifiOff size={14} className="text-bad" />}
          {latencyMs != null ? `${latencyMs} ms` : '—'}
        </span>
        <span className={clsx('flex items-center gap-1 font-mono',
          t?.low_batt && 'text-bad')}>
          <BatteryMedium size={15} />
          {t?.voltage != null ? `${t.voltage.toFixed(2)} V` : '—'}
          {t?.pct != null && <span className="text-ink-dim">({t.pct}%)</span>}
        </span>
        <button
          onClick={() => (estopActive ? ws.sendEstopRelease() : ws.sendEstop())}
          disabled={!authenticated}
          title={authenticated ? 'Emergency stop' : 'Unlock control on the Manual Control page first'}
          className={clsx(
            'flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-semibold transition-colors',
            !authenticated && 'opacity-40 cursor-not-allowed',
            estopActive
              ? 'bg-good/15 text-good hover:bg-good/25'
              : 'bg-bad/15 text-bad hover:bg-bad/25',
          )}
        >
          {estopActive ? <PlayCircle size={15} /> : <OctagonX size={15} />}
          {estopActive ? 'RESUME' : 'STOP'}
        </button>
      </div>
    </header>
  )
}
