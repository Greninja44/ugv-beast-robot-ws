import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Flag, Plus, Trash2, X } from 'lucide-react'
import { ws } from '../lib/ws'
import { apiFetch } from '../lib/api'
import { useChannelRef } from '../lib/useChannelRef'
import { useTeleop } from '../stores/teleop'
import { GlassCard } from '../components/GlassCard'
import { MapCanvas } from '../components/canvas/MapCanvas'
import type { NavState, OdomData, Waypoint } from '../lib/sensorTypes'

const STATUS_TONE: Record<string, string> = {
  idle: 'text-ink-dim',
  navigating: 'text-accent',
  succeeded: 'text-good',
  canceled: 'text-warn',
  aborted: 'text-bad',
  rejected: 'text-bad',
  error: 'text-bad',
}

export default function Nav() {
  const odomRef = useChannelRef<OdomData>('odom')
  const [nav, setNav] = useState<NavState | null>(null)
  const [waypoints, setWaypoints] = useState<Waypoint[]>([])
  const [wpName, setWpName] = useState('')
  const authenticated = useTeleop((s) => s.authenticated)

  useEffect(() => ws.on('nav', (data) => setNav(data as NavState)), [])

  const refreshWaypoints = () => apiFetch('/nav/waypoints').then((r) => r.json()).then(setWaypoints).catch(() => {})
  useEffect(() => { refreshWaypoints() }, [])

  const sendGoal = async (x: number, y: number, yaw = 0) => {
    if (!authenticated) return
    await apiFetch('/nav/goal', { method: 'POST', body: JSON.stringify({ x, y, yaw }) })
  }

  const cancelGoal = async () => {
    await apiFetch('/nav/cancel', { method: 'POST' })
  }

  const saveWaypointHere = async () => {
    const odom = odomRef.current
    if (!odom) return
    const name = wpName.trim() || `wp-${waypoints.length + 1}`
    await apiFetch('/nav/waypoints', {
      method: 'POST',
      body: JSON.stringify({ name, x: odom.x, y: odom.y, yaw: odom.yaw }),
    })
    setWpName('')
    refreshWaypoints()
  }

  const deleteWaypoint = async (id: string) => {
    await apiFetch(`/nav/waypoints/${id}`, { method: 'DELETE' })
    refreshWaypoints()
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
      className="grid gap-4 p-4 xl:grid-cols-4"
    >
      <GlassCard className="aspect-square xl:col-span-3 xl:aspect-auto">
        <MapCanvas odomRef={odomRef} waypoints={waypoints} onPickGoal={sendGoal} />
      </GlassCard>

      <GlassCard title="Navigation">
        <div className="flex items-center justify-between text-sm">
          <span className={STATUS_TONE[nav?.status ?? 'idle'] ?? 'text-ink'}>
            {nav?.status ?? 'idle'}
          </span>
          {nav?.distance_remaining != null && (
            <span className="font-mono text-xs text-ink-dim">{nav.distance_remaining.toFixed(2)} m</span>
          )}
        </div>
        {nav?.detail && <p className="mt-1 text-[11px] text-bad">{nav.detail}</p>}
        {nav?.status === 'navigating' && (
          <button onClick={cancelGoal}
                  className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg bg-bad/15
                             px-3 py-2 text-xs font-medium text-bad hover:bg-bad/25 transition-colors">
            <X size={14} /> Cancel goal
          </button>
        )}
        <p className="mt-3 text-[11px] text-ink-dim">
          {authenticated ? 'Click the map to send a goal.' : 'Unlock control (Manual Control page) to send goals.'}
        </p>
      </GlassCard>

      <GlassCard title="Waypoints" className="xl:col-span-4">
        <div className="mb-3 flex gap-2">
          <input
            value={wpName}
            onChange={(e) => setWpName(e.target.value)}
            placeholder="name (optional)"
            className="flex-1 rounded-lg border border-edge bg-white/5 px-3 py-1.5 text-sm outline-none focus:border-accent"
          />
          <button onClick={saveWaypointHere} disabled={!authenticated}
                  className="flex items-center gap-1.5 rounded-lg bg-accent/15 px-3 py-1.5 text-xs
                             font-medium text-accent hover:bg-accent/25 transition-colors disabled:opacity-40">
            <Plus size={14} /> Save current position
          </button>
        </div>
        {waypoints.length === 0 && <p className="text-xs text-ink-dim">No waypoints saved yet.</p>}
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {waypoints.map((wp) => (
            <div key={wp.id} className="flex items-center justify-between rounded-lg border border-edge px-3 py-2">
              <div>
                <div className="text-sm">{wp.name}</div>
                <div className="font-mono text-[11px] text-ink-dim">
                  ({wp.x.toFixed(2)}, {wp.y.toFixed(2)})
                </div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => sendGoal(wp.x, wp.y, wp.yaw)} disabled={!authenticated}
                        title="Navigate here"
                        className="rounded-lg p-1.5 text-accent hover:bg-accent/15 transition-colors disabled:opacity-40">
                  <Flag size={14} />
                </button>
                <button onClick={() => deleteWaypoint(wp.id)} title="Delete"
                        className="rounded-lg p-1.5 text-bad hover:bg-bad/15 transition-colors">
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </GlassCard>
    </motion.div>
  )
}
