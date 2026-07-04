import { useEffect, useRef } from 'react'
import { ws } from './ws'

/** Subscribes to a high-rate WS channel and stores the latest payload in a ref —
 * deliberately NOT React state, so a 5-10Hz stream doesn't trigger a re-render on
 * every frame. Canvas components read the ref inside their own rAF loop instead.
 * See docs/DASHBOARD_DESIGN.md §4 ("canvas + rAF, not React re-render"). */
export function useChannelRef<T>(channel: string) {
  const ref = useRef<T | null>(null)
  useEffect(() => ws.on(channel, (data) => { ref.current = data as T }), [channel])
  return ref
}
