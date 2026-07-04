import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Lightbulb, Play, Power, RotateCcw, Save, Square } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { GlassCard } from '../components/GlassCard'

type Actions = Record<string, boolean>

const SLAM_ACTIONS: { id: string; label: string }[] = [
  { id: 'slam_cartographer', label: 'Cartographer' },
  { id: 'slam_gmapping', label: 'GMapping' },
]

function ActionRow({ id, label, running, onStart, onStop }: {
  id: string; label: string; running: boolean
  onStart: (id: string) => void; onStop: (id: string) => void
}) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="flex items-center gap-2 text-sm">
        <span className={`h-1.5 w-1.5 rounded-full ${running ? 'bg-good animate-pulse' : 'bg-ink-dim/40'}`} />
        {label}
      </span>
      <button
        onClick={() => (running ? onStop(id) : onStart(id))}
        className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${running
          ? 'bg-bad/15 text-bad hover:bg-bad/25'
          : 'bg-accent/15 text-accent hover:bg-accent/25'}`}
      >
        {running ? <Square size={13} /> : <Play size={13} />}
        {running ? 'Stop' : 'Start'}
      </button>
    </div>
  )
}

function DisabledRow({ label, reason }: { label: string; reason: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 opacity-40" title={reason}>
      <span className="text-sm">{label}</span>
      <button disabled className="cursor-not-allowed rounded-lg border border-edge px-3 py-1.5 text-xs">
        N/A
      </button>
    </div>
  )
}

export default function Controls() {
  const [actions, setActions] = useState<Actions>({})
  const [mapName, setMapName] = useState('map')
  const [saveStatus, setSaveStatus] = useState<string | null>(null)
  const [ledOn, setLedOn] = useState(false)
  const [powerEnabled, setPowerEnabled] = useState(false)

  const refreshActions = () => apiFetch('/controls/actions').then((r) => r.json()).then(setActions).catch(() => {})

  useEffect(() => {
    refreshActions()
    const id = window.setInterval(refreshActions, 2000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    fetch('/api/controls/led').then((r) => r.json()).then((d) => setLedOn(d.on)).catch(() => {})
    fetch('/api/health').then((r) => r.json()).then((d) => setPowerEnabled(!!d.power_actions_enabled)).catch(() => {})
  }, [])

  const startAction = async (id: string) => {
    const r = await apiFetch(`/controls/actions/${id}/start`, { method: 'POST' })
    if (r.ok) setActions(await r.json())
  }
  const stopAction = async (id: string) => {
    const r = await apiFetch(`/controls/actions/${id}/stop`, { method: 'POST' })
    if (r.ok) setActions(await r.json())
  }

  const toggleLed = async () => {
    const r = await apiFetch('/controls/led', { method: 'PUT', body: JSON.stringify({ on: !ledOn }) })
    if (r.ok) setLedOn((await r.json()).on)
  }

  const saveMap = async () => {
    setSaveStatus('saving…')
    const r = await apiFetch('/controls/map/save', { method: 'POST', body: JSON.stringify({ name: mapName }) })
    if (r.ok) {
      const d = await r.json()
      setSaveStatus(`saved: ${d.path}`)
    } else {
      const d = await r.json().catch(() => ({}))
      setSaveStatus(`failed: ${d.detail ?? r.status}`)
    }
  }

  const powerAction = async (action: 'reboot' | 'shutdown') => {
    if (!window.confirm(`Really ${action} the robot? This will end the session.`)) return
    await apiFetch(`/system/${action}`, { method: 'POST' })
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
      className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <GlassCard title="SLAM">
        {SLAM_ACTIONS.map((a) => (
          <ActionRow key={a.id} id={a.id} label={a.label} running={!!actions[a.id]}
                     onStart={startAction} onStop={stopAction} />
        ))}
        <p className="mt-2 text-[11px] text-ink-dim">
          Runs the vendor's own SLAM launch files directly — nothing modified.
        </p>
      </GlassCard>

      <GlassCard title="Navigation">
        <ActionRow id="nav2" label="Nav2 stack" running={!!actions.nav2}
                   onStart={startAction} onStop={stopAction} />
      </GlassCard>

      <GlassCard title="Map">
        <div className="flex gap-2">
          <input
            value={mapName}
            onChange={(e) => setMapName(e.target.value)}
            placeholder="map name"
            className="flex-1 rounded-lg border border-edge bg-white/5 px-3 py-1.5 text-sm outline-none focus:border-accent"
          />
          <button onClick={saveMap}
                  className="flex items-center gap-1.5 rounded-lg bg-accent/15 px-3 py-1.5 text-xs
                             font-medium text-accent hover:bg-accent/25 transition-colors">
            <Save size={14} /> Save
          </button>
        </div>
        {saveStatus && <p className="mt-2 break-all text-[11px] text-ink-dim">{saveStatus}</p>}
        <p className="mt-2 text-[11px] text-ink-dim">
          Saves via Nav2's standard map_saver_server (requires SLAM running) into the
          vendor's own maps directory.
        </p>
      </GlassCard>

      <GlassCard title="Lighting">
        <button
          onClick={toggleLed}
          className={`flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-sm
                     font-medium transition-colors ${ledOn
            ? 'bg-warn/15 text-warn hover:bg-warn/25'
            : 'border border-edge text-ink-dim hover:text-ink'}`}
        >
          <Lightbulb size={16} className={ledOn ? 'fill-warn' : ''} />
          {ledOn ? 'Lights ON' : 'Lights OFF'}
        </button>
      </GlassCard>

      <GlassCard title="Manipulator">
        <DisabledRow label="Center gimbal" reason="Gimbal was physically removed — arm mount planned" />
        <DisabledRow label="Reset odometry" reason="No vendor service exists for this" />
      </GlassCard>

      <GlassCard title="Power" className="border-bad/20">
        <div className="flex gap-2">
          <button
            onClick={() => powerAction('reboot')}
            disabled={!powerEnabled}
            title={powerEnabled ? 'Reboot the Pi' : 'Disabled — set allow_system_power_actions in dashboard.yaml'}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-edge py-2
                       text-xs text-ink-dim transition-colors enabled:hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
          >
            <RotateCcw size={14} /> Reboot
          </button>
          <button
            onClick={() => powerAction('shutdown')}
            disabled={!powerEnabled}
            title={powerEnabled ? 'Shut down the Pi' : 'Disabled — set allow_system_power_actions in dashboard.yaml'}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-bad/30 py-2
                       text-xs text-bad transition-colors enabled:hover:bg-bad/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Power size={14} /> Shutdown
          </button>
        </div>
        {!powerEnabled && (
          <p className="mt-2 text-[11px] text-ink-dim">
            Disabled by default. Enable via <code>allow_system_power_actions: true</code> in
            <code> dashboard.yaml</code> if you want these available.
          </p>
        )}
      </GlassCard>
    </motion.div>
  )
}
