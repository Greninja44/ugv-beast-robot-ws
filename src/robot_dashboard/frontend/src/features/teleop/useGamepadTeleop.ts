import { useEffect, useRef } from 'react'

const DEADZONE = 0.12
// Xbox/PS5 button indices for bumpers+triggers (standard mapping): hold one as the
// deadman, matching a physical "hold to drive" convention on real controllers.
const DEADMAN_BUTTONS = [4, 5, 6, 7]

function applyDeadzone(v: number): number {
  return Math.abs(v) < DEADZONE ? 0 : v
}

/** Xbox/PS5 controller (Gamepad API) → normalized (-1..1) lin/ang, deadman = bumper/trigger held. */
export function useGamepadTeleop(
  enabled: boolean,
  onInput: (lin: number, ang: number, deadman: boolean) => void,
) {
  const rafRef = useRef<number | null>(null)
  const lastDeadman = useRef(false)

  useEffect(() => {
    if (!enabled) return

    const tick = () => {
      const pads = navigator.getGamepads()
      const gp = Array.from(pads).find((p) => p && p.connected)
      if (gp) {
        // Cast to allow `?? 0`: TS types axes[i] as plain number, but a real gamepad
        // may report fewer axes than expected, making it undefined at runtime.
        const axisY = gp.axes[1] as number | undefined
        const axisX = gp.axes[0] as number | undefined
        const lin = applyDeadzone(-(axisY ?? 0))
        const ang = applyDeadzone(-(axisX ?? 0))
        const deadman = gp.buttons.some((b, i) => DEADMAN_BUTTONS.includes(i) && b.pressed)
        if (deadman || lastDeadman.current) onInput(lin, ang, deadman)
        lastDeadman.current = deadman
      } else if (lastDeadman.current) {
        onInput(0, 0, false)
        lastDeadman.current = false
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      if (lastDeadman.current) {
        onInput(0, 0, false)
        lastDeadman.current = false
      }
    }
  }, [enabled, onInput])
}
