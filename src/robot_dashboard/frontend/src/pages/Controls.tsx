import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { ChevronDown, Lightbulb, Play, Power, RotateCcw, Save, Square, XCircle } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { ws } from '../lib/ws'
import type { SkillState } from '../lib/sensorTypes'
import { GlassCard } from '../components/GlassCard'

const SKILLS = ['stop', 'demo', 'goto', 'rotate360', 'look_around', 'explore_room'] as const

function SkillsCard() {
  const [skill, setSkill] = useState<string>(SKILLS[0])
  const [x, setX] = useState('1.0')
  const [y, setY] = useState('0.0')
  const [yaw, setYaw] = useState('0.0')
  const [state, setState] = useState<SkillState | null>(null)

  useEffect(() => ws.on('skill', (data) => setState(data as SkillState)), [])

  const running = state?.status === 'running'

  const run = () => {
    const args = skill === 'goto' ? [`x=${x}`, `y=${y}`, `yaw=${yaw}`] : []
    // Clicking Run IS the human granting autonomous authority — so set an autonomous
    // mode first (skills are gated on /robot/mode) instead of making the user also
    // remember to flip the header pill. 'stop' needs no authority. Small delay lets
    // the mode change propagate to skill_server's /robot/mode subscription before the
    // goal lands (otherwise the goal can race ahead of the mode update and get rejected).
    if (skill === 'stop') {
      ws.runSkill(skill, args)
      return
    }
    ws.setMode(skill === 'explore_room' ? 'explore' : 'ai')
    window.setTimeout(() => ws.runSkill(skill, args), 600)
  }

  return (
    <GlassCard title="Skills (RunSkill)">
      <div className="flex gap-2">
        <select
          value={skill}
          onChange={(e) => setSkill(e.target.value)}
          disabled={running}
          className="flex-1 rounded-lg border border-edge bg-white/5 px-3 py-1.5 text-sm outline-none focus:border-accent disabled:opacity-50"
        >
          {SKILLS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {running ? (
          <button onClick={() => ws.cancelSkill()}
                  className="flex items-center gap-1.5 rounded-lg bg-bad/15 px-3 py-1.5 text-xs
                             font-medium text-bad hover:bg-bad/25 transition-colors">
            <XCircle size={14} /> Cancel
          </button>
        ) : (
          <button onClick={run}
                  className="flex items-center gap-1.5 rounded-lg bg-accent/15 px-3 py-1.5 text-xs
                             font-medium text-accent hover:bg-accent/25 transition-colors">
            <Play size={14} /> Run
          </button>
        )}
      </div>

      {skill === 'goto' && !running && (
        <div className="mt-2 flex gap-2">
          {([['x', x, setX], ['y', y, setY], ['yaw', yaw, setYaw]] as const).map(([label, val, set]) => (
            <input key={label} value={val} onChange={(e) => set(e.target.value)}
                   placeholder={label}
                   className="w-0 flex-1 rounded-lg border border-edge bg-white/5 px-2 py-1 text-xs outline-none focus:border-accent" />
          ))}
        </div>
      )}

      {state && state.skill && (
        <div className="mt-3 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-ink-dim">{state.skill}</span>
            <span className={
              state.status === 'succeeded' ? 'text-good'
                : ['aborted', 'rejected', 'error'].includes(state.status) ? 'text-bad'
                  : 'text-ink-dim'
            }>{state.status}</span>
          </div>
          {state.progress != null && (
            <div className="mt-1 h-1 rounded-full bg-white/5">
              <div className="h-1 rounded-full bg-accent transition-all"
                   style={{ width: `${Math.round(state.progress * 100)}%` }} />
            </div>
          )}
          {(state.feedback || state.result_detail) && (
            <p className="mt-1 break-all text-[11px] text-ink-dim">
              {state.feedback ?? state.result_detail}
            </p>
          )}
        </div>
      )}
      <p className="mt-2 text-[11px] text-ink-dim">
        Run automatically grants autonomous authority (sets /robot/mode). Grabbing the
        joystick or hitting e-stop takes it back and stops the skill.
      </p>
    </GlassCard>
  )
}

type Actions = Record<string, boolean>

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

export default function Controls() {
  const [actions, setActions] = useState<Actions>({})
  const [mapName, setMapName] = useState('map')
  const [saveStatus, setSaveStatus] = useState<string | null>(null)
  const [ledOn, setLedOn] = useState(false)
  const [powerEnabled, setPowerEnabled] = useState(false)
  const [skillState, setSkillState] = useState<SkillState | null>(null)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  useEffect(() => ws.on('skill', (data) => setSkillState(data as SkillState)), [])

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

  // One-click autonomous exploration: bring up the SLAM+Nav2 stack, grant authority,
  // and launch the skill. explore_room waits for SLAM's map->base_link TF internally,
  // so it's fine to fire it right after the launch starts (it won't race ahead).
  const autoExplore = async () => {
    if (!actions.explore) {
      const r = await apiFetch('/controls/actions/explore/start', { method: 'POST' })
      if (r.ok) setActions(await r.json())
    }
    ws.setMode('explore')
    window.setTimeout(() => ws.runSkill('explore_room', []), 800)
  }
  const stopExplore = async () => {
    ws.cancelSkill()
    ws.setMode('idle')
    await stopAction('explore')
  }

  const exploring = skillState?.skill === 'explore_room' && skillState.status === 'running'

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
      className="grid gap-4 p-4"
    >
      {/* Primary flow: this is the only thing most sessions need. */}
      <GlassCard title="Explore & map this room" className="border-accent/30">
        {exploring ? (
          <button onClick={stopExplore}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-bad/30 bg-bad/10
                             py-3 text-sm font-semibold text-bad hover:bg-bad/20 transition-colors">
            <Square size={16} /> Stop exploring
          </button>
        ) : (
          <button onClick={autoExplore}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent/20 py-3
                             text-sm font-semibold text-accent hover:bg-accent/30 transition-colors">
            <Play size={16} /> Explore this room
          </button>
        )}
        <p className="mt-2 text-[11px] text-ink-dim">
          One click: starts live SLAM + Nav2, grants autonomous authority, and sends the
          robot off to drive and map the room on its own. Grab the joystick or hit e-stop
          to take back control.
        </p>
        {skillState?.skill === 'explore_room' && (
          <div className="mt-3 rounded-lg bg-white/5 p-2 text-xs">
            <span className={
              skillState.status === 'succeeded' ? 'text-good'
                : ['aborted', 'rejected', 'error'].includes(skillState.status) ? 'text-bad'
                  : 'text-ink-dim'
            }>{skillState.status}</span>
            {(skillState.feedback || skillState.result_detail) && (
              <p className="mt-1 break-all text-[11px] text-ink-dim">
                {skillState.feedback ?? skillState.result_detail}
              </p>
            )}
          </div>
        )}

        <div className="mt-4 flex gap-2 border-t border-edge pt-3">
          <input
            value={mapName}
            onChange={(e) => setMapName(e.target.value)}
            placeholder="map name"
            className="flex-1 rounded-lg border border-edge bg-white/5 px-3 py-1.5 text-sm outline-none focus:border-accent"
          />
          <button onClick={saveMap}
                  className="flex items-center gap-1.5 rounded-lg bg-accent/15 px-3 py-1.5 text-xs
                             font-medium text-accent hover:bg-accent/25 transition-colors">
            <Save size={14} /> Save map
          </button>
        </div>
        {saveStatus && <p className="mt-2 break-all text-[11px] text-ink-dim">{saveStatus}</p>}
      </GlassCard>

      <GlassCard title="Lighting" className="max-w-xs">
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

      {/* Everything below is power-user / debugging territory — collapsed by
          default so the common case (explore & map) isn't buried under raw
          per-subsystem launch buttons. */}
      <button
        onClick={() => setAdvancedOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-ink-dim hover:text-ink transition-colors"
      >
        <ChevronDown size={14} className={`transition-transform ${advancedOpen ? 'rotate-180' : ''}`} />
        {advancedOpen ? 'Hide advanced controls' : 'Show advanced controls'}
      </button>

      {advancedOpen && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <GlassCard title="Base driver">
            <ActionRow id="base" label="Bringup (driver + lidar)" running={!!actions.base}
                       onStart={startAction} onStop={stopAction} />
            <p className="mt-2 text-[11px] text-ink-dim">
              Starts automatically on boot. Owns the ESP32 serial — teleop, lights and
              sensors need this running. Starting SLAM below takes it over automatically.
            </p>
          </GlassCard>

          <GlassCard title="Manual SLAM (drive yourself, build + save a map)">
            <ActionRow id="slam_cartographer" label="Cartographer" running={!!actions.slam_cartographer}
                       onStart={startAction} onStop={stopAction} />
            <p className="mt-2 text-[11px] text-ink-dim">
              Drive around yourself (WASD/joystick) while this builds the map, then Save
              above. For hands-off mapping use "Explore this room" instead.
            </p>
          </GlassCard>

          <GlassCard title="Navigation (drive within a saved map)">
            <ActionRow id="nav2" label="Nav2 (amcl)" running={!!actions.nav2}
                       onStart={startAction} onStop={stopAction} />
            <p className="mt-2 text-[11px] text-ink-dim">
              For a room you've already mapped and saved. Needs a saved map to be useful —
              build one above first.
            </p>
          </GlassCard>

          <SkillsCard />

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
        </div>
      )}
    </motion.div>
  )
}
