import { ws } from './ws'
import type { OdomData } from './sensorTypes'

/** Module-level (not component-local) trail buffer: survives navigating away from
 * and back to the Sensors page. A React ref reset to empty on every remount is
 * what made the trail look "broken" after driving from the Teleop page and
 * switching back — this subscribes once for the life of the app instead. */
const TRAIL_MAX = 600 // ~1min at ~10Hz, gated to ~6-7Hz pushes below

export interface TrailPoint { x: number; y: number }

export const odomTrail: TrailPoint[] = []

let lastPush = 0
// Deliberately never unsubscribed: this is a session-lifetime accumulator, not
// tied to a component's mount/unmount. Cost is one lazy 'odom' channel
// subscription (10Hz) kept alive for the rest of the session once the Sensors
// page has been opened at least once — cheap, and the whole point of this file.
ws.on('odom', (raw) => {
  const data = raw as OdomData
  const now = performance.now()
  if (now - lastPush < 150) return
  lastPush = now
  odomTrail.push({ x: data.x, y: data.y })
  if (odomTrail.length > TRAIL_MAX) odomTrail.shift()
})
