import { motion } from 'framer-motion'
import { useRobot } from '../stores/robot'
import { GlassCard, Stat } from '../components/GlassCard'

function BatteryBar({ pct, low }: { pct: number | null; low: boolean }) {
  const tone = low ? 'bg-bad' : (pct ?? 0) < 40 ? 'bg-warn' : 'bg-good'
  return (
    <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-white/5">
      <div className={`h-full rounded-full transition-all duration-700 ${tone}`}
           style={{ width: `${pct ?? 0}%` }} />
    </div>
  )
}

export default function Dashboard() {
  const t = useRobot((s) => s.telemetry)

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15 }}
      className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-4"
    >
      <GlassCard title="Power" className="xl:col-span-1">
        <Stat label="Battery" value={t?.voltage?.toFixed(2)} unit="V"
              tone={t?.low_batt ? 'bad' : 'default'} />
        <BatteryBar pct={t?.pct ?? null} low={!!t?.low_batt} />
        <div className="mt-1 text-right text-xs text-ink-dim">{t?.pct ?? '—'}%</div>
      </GlassCard>

      <GlassCard title="Motion">
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Linear" value={t?.lin?.toFixed(2)} unit="m/s" />
          <Stat label="Angular" value={t?.ang?.toFixed(2)} unit="rad/s" />
        </div>
      </GlassCard>

      <GlassCard title="Compute">
        <div className="grid grid-cols-3 gap-3">
          <Stat label="CPU" value={t?.cpu} unit="%" tone={(t?.cpu ?? 0) > 85 ? 'warn' : 'default'} />
          <Stat label="Mem" value={t?.mem} unit="%" />
          <Stat label="Temp" value={t?.temp?.toFixed(0)} unit="°C"
                tone={(t?.temp ?? 0) > 75 ? 'warn' : 'default'} />
        </div>
      </GlassCard>

      <GlassCard title="ROS Graph">
        <div className="grid grid-cols-3 gap-3">
          <Stat label="Status" value={t ? (t.ros ? 'UP' : 'DOWN') : null}
                tone={t?.ros ? 'good' : 'bad'} />
          <Stat label="Nodes" value={t?.nodes} />
          <Stat label="Topics" value={t?.topics} />
        </div>
      </GlassCard>

      <GlassCard title="Pose (odom)" className="md:col-span-2">
        <div className="grid grid-cols-3 gap-3">
          <Stat label="X" value={t?.pose?.x.toFixed(2)} unit="m" />
          <Stat label="Y" value={t?.pose?.y.toFixed(2)} unit="m" />
          <Stat label="Yaw" value={t?.pose ? (t.pose.yaw * 57.2958).toFixed(1) : null} unit="°" />
        </div>
      </GlassCard>

      <GlassCard title="Localization" className="md:col-span-2">
        <Stat label="Mode" value={t?.loc?.replace('_', ' ')}
              tone={t?.loc === 'map' ? 'good' : 'default'} />
        <p className="mt-2 text-xs leading-relaxed text-ink-dim">
          “odom only” until SLAM / Nav2 publish the <code>map → odom</code> transform.
        </p>
      </GlassCard>
    </motion.div>
  )
}
