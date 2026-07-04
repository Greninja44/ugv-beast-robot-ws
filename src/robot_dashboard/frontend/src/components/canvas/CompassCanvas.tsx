import type { MutableRefObject } from 'react'
import { useRafCanvas } from './useRafCanvas'
import type { ImuData } from '../../lib/sensorTypes'

/** Heading compass rose driven by the IMU's fused orientation (yaw). */
export function CompassCanvas({ dataRef }: { dataRef: MutableRefObject<ImuData | null> }) {
  const canvasRef = useRafCanvas((ctx, w, h) => {
    const cx = w / 2, cy = h / 2
    const r = Math.min(w, h) / 2 - 10
    const yaw = dataRef.current?.yaw ?? 0

    ctx.strokeStyle = 'rgba(255,255,255,0.15)'
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke()

    ctx.fillStyle = 'rgba(230,237,243,0.7)'
    ctx.font = '11px ui-sans-serif, system-ui'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const labels: [string, number][] = [['N', -Math.PI / 2], ['E', 0], ['S', Math.PI / 2], ['W', Math.PI]]
    for (const [label, a] of labels) {
      // screen angle = -yaw so the needle rotates with the robot's heading
      const angle = a - yaw
      ctx.fillText(label, cx + (r - 12) * Math.cos(angle), cy + (r - 12) * Math.sin(angle))
    }

    // Needle: forward = -90deg (up) rotated by -yaw
    const needleAngle = -Math.PI / 2 - yaw
    ctx.strokeStyle = '#38bdf8'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(cx, cy)
    ctx.lineTo(cx + (r - 20) * Math.cos(needleAngle), cy + (r - 20) * Math.sin(needleAngle))
    ctx.stroke()
    ctx.lineWidth = 1

    ctx.fillStyle = '#e6edf3'
    ctx.beginPath(); ctx.arc(cx, cy, 3, 0, Math.PI * 2); ctx.fill()

    ctx.fillStyle = 'rgba(230,237,243,0.85)'
    ctx.font = '13px ui-monospace, monospace'
    const deg = Math.round((((yaw * 180) / Math.PI) % 360 + 360) % 360)
    ctx.fillText(`${deg}°`, cx, cy + r + 14)
    ctx.textAlign = 'left'
    ctx.textBaseline = 'alphabetic'
  })

  return <canvas ref={canvasRef} className="h-full w-full rounded-xl" />
}
