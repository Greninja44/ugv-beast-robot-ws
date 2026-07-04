import { useCallback, useEffect, useRef, useState } from 'react'
import { useRafCanvas } from './useRafCanvas'
import type { MapMeta, OdomData, Waypoint } from '../../lib/sensorTypes'

const REFRESH_MS = 4000

interface Props {
  odomRef: React.MutableRefObject<OdomData | null>
  waypoints: Waypoint[]
  onPickGoal: (x: number, y: number) => void
}

/** Top-down occupancy-grid map. The bitmap refreshes on a slow poll (maps don't
 * change fast); the robot marker still updates every frame via the rAF loop,
 * same "canvas + ref, not React state" rule as the other sensor canvases. */
export function MapCanvas({ odomRef, waypoints, onPickGoal }: Props) {
  const bitmapRef = useRef<ImageBitmap | null>(null)
  const metaRef = useRef<MapMeta | null>(null)
  const fitRef = useRef<{ scale: number; offX: number; offY: number } | null>(null)
  const [available, setAvailable] = useState<boolean | null>(null)

  const refresh = useCallback(async () => {
    try {
      const r = await fetch('/api/map')
      if (!r.ok) { setAvailable(false); return }
      const meta: MapMeta = {
        width: Number(r.headers.get('X-Map-Width')),
        height: Number(r.headers.get('X-Map-Height')),
        resolution: Number(r.headers.get('X-Map-Resolution')),
        originX: Number(r.headers.get('X-Map-Origin-X')),
        originY: Number(r.headers.get('X-Map-Origin-Y')),
      }
      const blob = await r.blob()
      bitmapRef.current = await createImageBitmap(blob)
      metaRef.current = meta
      setAvailable(true)
    } catch {
      setAvailable(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = window.setInterval(refresh, REFRESH_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  // world (map frame) -> displayed-image pixel. The server flips the raw grid
  // vertically before sending (see bridge.py _on_map) so "up on screen = +Y";
  // this is the exact inverse of that transform.
  const worldToImagePx = useCallback((x: number, y: number) => {
    const meta = metaRef.current
    if (!meta) return null
    const rawRow = (y - meta.originY) / meta.resolution
    return {
      px: (x - meta.originX) / meta.resolution,
      py: meta.height - 1 - rawRow,
    }
  }, [])

  const imagePxToWorld = useCallback((px: number, py: number) => {
    const meta = metaRef.current
    if (!meta) return null
    const rawRow = meta.height - 1 - py
    return {
      x: meta.originX + px * meta.resolution,
      y: meta.originY + rawRow * meta.resolution,
    }
  }, [])

  const canvasRef = useRafCanvas((ctx, w, h) => {
    const bitmap = bitmapRef.current
    const meta = metaRef.current
    if (!bitmap || !meta) {
      ctx.fillStyle = 'rgba(230,237,243,0.5)'
      ctx.font = '13px ui-sans-serif, system-ui'
      ctx.textAlign = 'center'
      ctx.fillText('waiting for /map… (start SLAM on the Robot page)', w / 2, h / 2)
      ctx.textAlign = 'left'
      return
    }

    // Fit the map image into the canvas, preserving aspect ratio, centered.
    const scale = Math.min(w / meta.width, h / meta.height)
    const drawW = meta.width * scale, drawH = meta.height * scale
    const offX = (w - drawW) / 2, offY = (h - drawH) / 2
    ctx.drawImage(bitmap, offX, offY, drawW, drawH)

    const toCanvas = (x: number, y: number) => {
      const p = worldToImagePx(x, y)
      if (!p) return null
      return { cx: offX + p.px * scale, cy: offY + p.py * scale }
    }

    // Waypoints
    for (const wp of waypoints) {
      const p = toCanvas(wp.x, wp.y)
      if (!p) continue
      ctx.fillStyle = '#38bdf8'
      ctx.beginPath()
      ctx.arc(p.cx, p.cy, 5, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = 'rgba(230,237,243,0.8)'
      ctx.font = '10px ui-sans-serif, system-ui'
      ctx.fillText(wp.name, p.cx + 7, p.cy + 3)
    }

    // Robot marker
    const odom = odomRef.current
    if (odom) {
      const p = toCanvas(odom.x, odom.y)
      if (p) {
        ctx.save()
        ctx.translate(p.cx, p.cy)
        ctx.rotate(-odom.yaw - Math.PI / 2) // canvas Y grows downward -> flip like other views
        ctx.fillStyle = '#e6edf3'
        ctx.beginPath()
        ctx.moveTo(0, -9); ctx.lineTo(-6, 7); ctx.lineTo(6, 7)
        ctx.closePath()
        ctx.fill()
        ctx.restore()
      }
    }

    // Stash the fit transform so the click handler (DOM event, not rAF) can use it.
    fitRef.current = { scale, offX, offY }
  })

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    const fit = fitRef.current
    if (!canvas || !fit) return
    const rect = canvas.getBoundingClientRect()
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top
    const px = (cx - fit.offX) / fit.scale
    const py = (cy - fit.offY) / fit.scale
    const world = imagePxToWorld(px, py)
    if (world) onPickGoal(world.x, world.y)
  }

  return (
    <div className="relative h-full w-full">
      <canvas ref={canvasRef} onClick={handleClick} className="h-full w-full cursor-crosshair rounded-xl" />
      {available === false && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <p className="text-sm text-ink-dim">no map yet — start SLAM from the Robot Controls page</p>
        </div>
      )}
    </div>
  )
}
