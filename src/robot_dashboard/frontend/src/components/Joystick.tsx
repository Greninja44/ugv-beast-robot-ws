import { useCallback, useRef, useState } from 'react'

interface JoystickProps {
  onInput: (lin: number, ang: number, deadman: boolean) => void
  size?: number
  disabled?: boolean
}

/** Touch-first virtual joystick. Pointer down = deadman engaged; release snaps back to
 * center and immediately sends deadman:false so the server watchdog isn't relied on
 * for the common "let go" case. When `disabled`, pointer-events are cut at the DOM
 * level (not just re-routing the callback) so a stale drag can't linger. */
export function Joystick({ onInput, size = 160, disabled = false }: JoystickProps) {
  const baseRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [active, setActive] = useState(false)

  const update = useCallback((clientX: number, clientY: number) => {
    const base = baseRef.current
    if (!base) return
    const rect = base.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    let dx = (clientX - cx) / (rect.width / 2)
    let dy = (clientY - cy) / (rect.height / 2)
    const mag = Math.hypot(dx, dy)
    if (mag > 1) { dx /= mag; dy /= mag }
    setPos({ x: dx, y: dy })
    onInput(-dy, -dx, true) // up = forward(+lin); left = turn-left(+ang)
  }, [onInput])

  const start = (e: React.PointerEvent) => {
    ;(e.target as Element).setPointerCapture(e.pointerId)
    setActive(true)
    update(e.clientX, e.clientY)
  }
  const move = (e: React.PointerEvent) => {
    if (active) update(e.clientX, e.clientY)
  }
  const end = () => {
    setActive(false)
    setPos({ x: 0, y: 0 })
    onInput(0, 0, false)
  }

  const knob = size * 0.4
  const travel = (size - knob) / 2

  return (
    <div
      ref={baseRef}
      onPointerDown={disabled ? undefined : start}
      onPointerMove={disabled ? undefined : move}
      onPointerUp={disabled ? undefined : end}
      onPointerCancel={disabled ? undefined : end}
      className="glass relative touch-none select-none rounded-full transition-opacity"
      style={{ width: size, height: size, opacity: disabled ? 0.35 : 1, pointerEvents: disabled ? 'none' : 'auto' }}
    >
      <div
        className="absolute rounded-full bg-accent shadow-lg shadow-accent/30 transition-transform duration-75"
        style={{
          width: knob,
          height: knob,
          left: '50%',
          top: '50%',
          transform: `translate(-50%, -50%) translate(${pos.x * travel}px, ${pos.y * travel}px)`,
          opacity: active ? 1 : 0.6,
        }}
      />
    </div>
  )
}
