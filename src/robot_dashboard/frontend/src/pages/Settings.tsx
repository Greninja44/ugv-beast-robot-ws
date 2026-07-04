import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Check, KeyRound } from 'lucide-react'
import { ws } from '../lib/ws'
import { GlassCard, Stat } from '../components/GlassCard'

interface RosInfo {
  ros_domain_id: string
  rmw_implementation: string
  camera_topic: string
  read_only: boolean
}

export default function Settings() {
  const [info, setInfo] = useState<RosInfo | null>(null)
  const [tokenInput, setTokenInput] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetch('/api/system/ros-info').then((r) => r.json()).then(setInfo).catch(() => {})
    setTokenInput(ws.getToken() ?? '')
  }, [])

  const saveToken = () => {
    ws.setToken(tokenInput)
    setSaved(true)
    window.setTimeout(() => setSaved(false), 1500)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
      className="grid gap-4 p-4 md:grid-cols-2"
    >
      <GlassCard title="Control token">
        <p className="mb-3 text-xs text-ink-dim">
          Required to drive, e-stop, toggle lights, or manage SLAM/Nav2 — without it the
          dashboard is read-only. Configured on the robot in
          <code> robot_dashboard/config/dashboard.yaml</code>.
        </p>
        <div className="flex gap-2">
          <input
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="control token"
            className="flex-1 rounded-lg border border-edge bg-white/5 px-3 py-2 text-sm outline-none focus:border-accent"
          />
          <button
            onClick={saveToken}
            className="flex items-center gap-1.5 rounded-lg bg-accent/20 px-4 py-2 text-sm font-medium
                       text-accent hover:bg-accent/30 transition-colors"
          >
            {saved ? <Check size={15} /> : <KeyRound size={15} />}
            {saved ? 'Saved' : 'Save'}
          </button>
        </div>
      </GlassCard>

      <GlassCard title="Connection">
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Mode" value={info ? (info.read_only ? 'Read-only' : 'Control unlocked') : null}
                tone={info?.read_only ? 'warn' : 'good'} />
          <Stat label="ROS Domain" value={info?.ros_domain_id} />
        </div>
        <div className="mt-3">
          <div className="text-[11px] uppercase tracking-wider text-ink-dim">RMW / DDS</div>
          <div className="font-mono text-sm">{info?.rmw_implementation ?? '—'}</div>
        </div>
        <div className="mt-3">
          <div className="text-[11px] uppercase tracking-wider text-ink-dim">Camera topic</div>
          <div className="font-mono text-sm">{info?.camera_topic ?? '—'}</div>
        </div>
      </GlassCard>

      <GlassCard title="About" className="md:col-span-2 text-xs text-ink-dim">
        <p>
          robot_dashboard — FastAPI + rclpy backend, React frontend. Talks to the vendor UGV
          Beast stack only via ROS topics/services/actions, never by modifying vendor code.
        </p>
        <p className="mt-2">
          Theme, joystick remapping, and keybinding customization aren't built yet — this page
          will grow as those land.
        </p>
      </GlassCard>
    </motion.div>
  )
}
