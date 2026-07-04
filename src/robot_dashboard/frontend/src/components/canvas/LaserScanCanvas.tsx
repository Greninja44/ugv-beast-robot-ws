import type { MutableRefObject } from 'react'
import { useRafCanvas } from './useRafCanvas'
import type { ScanData } from '../../lib/sensorTypes'

/** Top-down LiDAR view, robot at center, +x (forward) pointing up. Reads the
 * latest scan from a ref every animation frame — no React state involved, so this
 * stays smooth at 5Hz+ on a phone even while the rest of the page is static. */
export function LaserScanCanvas({ dataRef }: { dataRef: MutableRefObject<ScanData | null> }) {
  const canvasRef = useRafCanvas((ctx, w, h) => {
    const cx = w / 2, cy = h / 2
    const data = dataRef.current

    // Scale to what the room actually looks like, not the sensor's rated max range
    // (rmax is often a generous spec, e.g. 25m for a lidar that's really only
    // reliable to a few metres indoors — a small room would render as a speck).
    let observedMax = 0
    if (data) {
      for (const mm of data.ranges) if (mm > observedMax) observedMax = mm
    }
    const maxRange = observedMax > 0 ? Math.max(observedMax / 1000 * 1.15, 1.5) : (data?.rmax ?? 8)
    const scale = (Math.min(w, h) / 2 - 12) / maxRange

    // Range rings
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'
    ctx.fillStyle = 'rgba(255,255,255,0.35)'
    ctx.font = '10px ui-sans-serif, system-ui'
    const rings = 4
    for (let i = 1; i <= rings; i++) {
      const r = (maxRange * i) / rings
      ctx.beginPath()
      ctx.arc(cx, cy, r * scale, 0, Math.PI * 2)
      ctx.stroke()
      ctx.fillText(`${r.toFixed(1)}m`, cx + 4, cy - r * scale - 2)
    }

    // Heading crosshair
    ctx.strokeStyle = 'rgba(255,255,255,0.12)'
    ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, h); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(0, cy); ctx.lineTo(w, cy); ctx.stroke()

    // Scan points: screen x = forward(+x, up), screen y = left(+y)... robot frame:
    // range at `angle` -> (rangeM*cos(angle), rangeM*sin(angle)) in robot XY (x fwd, y left)
    if (data && data.ranges.length > 0) {
      ctx.fillStyle = '#38bdf8'
      for (let i = 0; i < data.ranges.length; i++) {
        const mm = data.ranges[i]
        if (!mm) continue
        const rangeM = mm / 1000
        const angle = data.amin + i * data.ainc
        const rx = rangeM * Math.cos(angle)
        const ry = rangeM * Math.sin(angle)
        const px = cx - ry * scale // +y (left) -> screen left
        const py = cy - rx * scale // +x (forward) -> screen up
        ctx.beginPath()
        ctx.arc(px, py, 1.6, 0, Math.PI * 2)
        ctx.fill()
      }
    }

    // Robot marker (triangle pointing "up" = forward)
    ctx.fillStyle = '#e6edf3'
    ctx.beginPath()
    ctx.moveTo(cx, cy - 8)
    ctx.lineTo(cx - 6, cy + 6)
    ctx.lineTo(cx + 6, cy + 6)
    ctx.closePath()
    ctx.fill()

    if (!data) {
      ctx.fillStyle = 'rgba(230,237,243,0.5)'
      ctx.font = '13px ui-sans-serif, system-ui'
      ctx.textAlign = 'center'
      ctx.fillText('waiting for /scan…', cx, cy + 40)
      ctx.textAlign = 'left'
    }
  })

  return <canvas ref={canvasRef} className="h-full w-full rounded-xl" />
}
