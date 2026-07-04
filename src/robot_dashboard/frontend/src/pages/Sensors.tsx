import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Wifi, WifiOff } from 'lucide-react'
import clsx from 'clsx'
import { GlassCard, Stat } from '../components/GlassCard'
import { LaserScanCanvas } from '../components/canvas/LaserScanCanvas'
import { CompassCanvas } from '../components/canvas/CompassCanvas'
import { OdomTrailCanvas } from '../components/canvas/OdomTrailCanvas'
import { TfHealthTable } from '../components/TfHealthTable'
import { useChannelRef } from '../lib/useChannelRef'
import { useRobot } from '../stores/robot'
import type { ImuData, OdomData, ScanData } from '../lib/sensorTypes'

function ConnectionQuality() {
  const { status, latencyMs } = useRobot()
  const online = status === 'online'
  const tone = !online ? 'bad' : latencyMs == null ? 'default' : latencyMs < 100 ? 'good' : latencyMs < 300 ? 'warn' : 'bad'
  const toneCls = { default: 'text-ink', good: 'text-good', warn: 'text-warn', bad: 'text-bad' }[tone]
  return (
    <div className="flex items-center gap-2">
      {online ? <Wifi size={16} /> : <WifiOff size={16} className="text-bad" />}
      <span className={clsx('font-mono text-sm', toneCls)}>
        {online ? (latencyMs != null ? `${latencyMs} ms` : '—') : 'offline'}
      </span>
    </div>
  )
}

export default function Sensors() {
  const scanRef = useChannelRef<ScanData>('scan')
  const imuRef = useChannelRef<ImuData>('imu')
  const odomRef = useChannelRef<OdomData>('odom')

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
      className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-4"
    >
      <GlassCard title="LaserScan" className="md:col-span-2 xl:col-span-2 aspect-square">
        <LaserScanCanvas dataRef={scanRef} />
      </GlassCard>

      <GlassCard title="Compass (IMU heading)" className="aspect-square">
        <CompassCanvas dataRef={imuRef} />
      </GlassCard>

      <GlassCard title="Odometry trail" className="aspect-square">
        <OdomTrailCanvas dataRef={odomRef} />
      </GlassCard>

      <GlassCard title="IMU raw">
        <ImuReadout dataRef={imuRef} />
      </GlassCard>

      <GlassCard title="Odometry">
        <OdomReadout dataRef={odomRef} />
      </GlassCard>

      <GlassCard title="TF status">
        <TfHealthTable />
      </GlassCard>

      <GlassCard title="Connection quality">
        <ConnectionQuality />
      </GlassCard>
    </motion.div>
  )
}

// Small numeric readouts poll the same refs on an interval — cheap, low-rate,
// no need for a canvas here (a few numbers re-rendering at ~4Hz is fine).
function ImuReadout({ dataRef }: { dataRef: React.MutableRefObject<ImuData | null> }) {
  const [tick, setTick] = useState(0)
  useEffect(() => { const id = setInterval(() => setTick((t) => t + 1), 250); return () => clearInterval(id) }, [])
  const d = dataRef.current
  return (
    <div className="grid grid-cols-3 gap-3" key={tick}>
      <Stat label="Accel X" value={d?.ax.toFixed(2)} unit="m/s²" />
      <Stat label="Accel Y" value={d?.ay.toFixed(2)} unit="m/s²" />
      <Stat label="Accel Z" value={d?.az.toFixed(2)} unit="m/s²" />
      <Stat label="Gyro X" value={d?.gx.toFixed(2)} unit="rad/s" />
      <Stat label="Gyro Y" value={d?.gy.toFixed(2)} unit="rad/s" />
      <Stat label="Gyro Z" value={d?.gz.toFixed(2)} unit="rad/s" />
    </div>
  )
}

function OdomReadout({ dataRef }: { dataRef: React.MutableRefObject<OdomData | null> }) {
  const [tick, setTick] = useState(0)
  useEffect(() => { const id = setInterval(() => setTick((t) => t + 1), 250); return () => clearInterval(id) }, [])
  const d = dataRef.current
  return (
    <div className="grid grid-cols-3 gap-3" key={tick}>
      <Stat label="X" value={d?.x.toFixed(2)} unit="m" />
      <Stat label="Y" value={d?.y.toFixed(2)} unit="m" />
      <Stat label="Yaw" value={d ? ((d.yaw * 180) / Math.PI).toFixed(0) : null} unit="°" />
      <Stat label="Linear" value={d?.lin.toFixed(2)} unit="m/s" />
      <Stat label="Angular" value={d?.ang.toFixed(2)} unit="rad/s" />
    </div>
  )
}
