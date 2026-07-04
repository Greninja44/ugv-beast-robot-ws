import { useEffect, useRef } from 'react'

const DRIVE_KEYS = new Set([
  'w', 'W', 'a', 'A', 's', 'S', 'd', 'D',
  'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
])

/** WASD / arrow keys → normalized (-1..1) lin/ang, deadman = any drive key held. */
export function useKeyboardTeleop(
  enabled: boolean,
  onInput: (lin: number, ang: number, deadman: boolean) => void,
) {
  const held = useRef(new Set<string>())

  useEffect(() => {
    if (!enabled) return

    const publish = () => {
      const k = held.current
      const lin = (k.has('w') || k.has('W') || k.has('ArrowUp') ? 1 : 0)
        - (k.has('s') || k.has('S') || k.has('ArrowDown') ? 1 : 0)
      const ang = (k.has('a') || k.has('A') || k.has('ArrowLeft') ? 1 : 0)
        - (k.has('d') || k.has('D') || k.has('ArrowRight') ? 1 : 0)
      onInput(lin, ang, k.size > 0)
    }

    const onKeyDown = (e: KeyboardEvent) => {
      if (!DRIVE_KEYS.has(e.key)) return
      e.preventDefault()
      held.current.add(e.key)
      publish()
    }
    const onKeyUp = (e: KeyboardEvent) => {
      if (!DRIVE_KEYS.has(e.key)) return
      held.current.delete(e.key)
      publish()
    }
    const onBlur = () => {
      if (held.current.size === 0) return
      held.current.clear()
      onInput(0, 0, false)
    }

    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', onBlur)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', onBlur)
      if (held.current.size > 0) {
        held.current.clear()
        onInput(0, 0, false)
      }
    }
  }, [enabled, onInput])
}
