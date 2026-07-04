import { useEffect, useRef } from 'react'

/** Wires a <canvas> to a rAF draw loop with DPR-aware sizing and auto-resize.
 * `draw` receives the 2D context and the canvas's CSS-pixel width/height (not the
 * backing-store size) so callers can draw in intuitive coordinates. */
export function useRafCanvas(draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const drawRef = useRef(draw)
  drawRef.current = draw

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.max(1, window.devicePixelRatio || 1)
    const resize = () => {
      const { width, height } = canvas.getBoundingClientRect()
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    let raf = 0
    const tick = () => {
      const { width, height } = canvas.getBoundingClientRect()
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      try {
        drawRef.current(ctx, width, height)
      } catch (err) {
        // A bug in one widget's draw function must not permanently freeze it (the
        // old behavior: an uncaught throw here skipped the next rAF schedule below,
        // silently killing the whole canvas until reload). Log and keep animating.
        console.error('[useRafCanvas] draw() threw, will retry next frame:', err)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
    }
  }, [])

  return canvasRef
}
