import type { MutableRefObject } from 'react'
import { useRafCanvas } from './useRafCanvas'
import { odomTrail } from '../../lib/odomTrail'
import type { OdomData } from '../../lib/sensorTypes'

/** Rolling trail of the robot's odom-frame position, robot marker with heading
 * arrow at the latest pose. Auto-scales to fit whatever area has been covered.
 * The trail itself lives in a module-level store (lib/odomTrail.ts) so it
 * survives navigating to another page (e.g. Teleop) and back — a React ref here
 * would reset to empty on every remount, which looked like a "broken" trail
 * after driving from the Teleop page. */
export function OdomTrailCanvas({ dataRef }: { dataRef: MutableRefObject<OdomData | null> }) {
  const canvasRef = useRafCanvas((ctx, w, h) => {
    const pts = odomTrail
    const d = dataRef.current
    const cx = w / 2, cy = h / 2

    if (pts.length === 0 || !d) {
      ctx.fillStyle = 'rgba(230,237,243,0.5)'
      ctx.font = '13px ui-sans-serif, system-ui'
      ctx.textAlign = 'center'
      ctx.fillText('waiting for /odom…', cx, cy)
      ctx.textAlign = 'left'
      return
    }

    // Fit all points + a margin into the canvas, scaled uniformly.
    let minX = d.x, maxX = d.x, minY = d.y, maxY = d.y
    for (const p of pts) {
      minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x)
      minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y)
    }
    const spanX = Math.max(maxX - minX, 0.5)
    const spanY = Math.max(maxY - minY, 0.5)
    const scale = Math.min((w - 40) / spanX, (h - 40) / spanY)
    const midX = (minX + maxX) / 2
    const midY = (minY + maxY) / 2
    const toScreen = (x: number, y: number) => ({
      sx: cx - (y - midY) * scale,
      sy: cy - (x - midX) * scale,
    })

    ctx.strokeStyle = 'rgba(56,189,248,0.6)'
    ctx.lineWidth = 2
    ctx.beginPath()
    pts.forEach((p, i) => {
      const { sx, sy } = toScreen(p.x, p.y)
      if (i === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy)
    })
    ctx.stroke()
    ctx.lineWidth = 1

    const { sx, sy } = toScreen(d.x, d.y)
    ctx.save()
    ctx.translate(sx, sy)
    ctx.rotate(-d.yaw - Math.PI / 2)
    ctx.fillStyle = '#e6edf3'
    ctx.beginPath()
    ctx.moveTo(0, -8); ctx.lineTo(-6, 6); ctx.lineTo(6, 6)
    ctx.closePath()
    ctx.fill()
    ctx.restore()
  })

  return <canvas ref={canvasRef} className="h-full w-full rounded-xl" />
}
