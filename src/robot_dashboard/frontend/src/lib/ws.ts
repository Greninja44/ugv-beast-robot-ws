/* Typed WebSocket client: auto-reconnect with backoff, channel refcounting,
 * automatic resubscribe after reconnect, 5s latency probes, and the teleop/e-stop
 * control ops (Phase 2). High-rate channels write into per-channel listeners so
 * canvas renderers can read them at rAF speed without triggering React. */
import { useRobot } from '../stores/robot'
import { useTeleop } from '../stores/teleop'

type Listener = (data: unknown) => void

const TOKEN_KEY = 'dash_token'

function wsUrl(): string {
  const base = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? `${base}?token=${encodeURIComponent(token)}` : base
}

class WsClient {
  private sock: WebSocket | null = null
  private wanted = new Map<string, Set<Listener>>() // channel -> listeners
  private retry = 500
  private pingTimer: number | undefined

  connect() {
    if (this.sock && this.sock.readyState <= WebSocket.OPEN) return
    useRobot.getState().setStatus('connecting')
    this.sock = new WebSocket(wsUrl())

    this.sock.onopen = () => {
      this.retry = 500
      useRobot.getState().setStatus('online')
      for (const ch of this.wanted.keys()) this.send({ op: 'sub', ch })
      this.pingTimer = window.setInterval(
        () => this.send({ op: 'ping', t: performance.now() }), 5000)
    }

    this.sock.onmessage = (ev) => {
      const m = JSON.parse(ev.data)
      switch (m.op) {
        case 'msg':
          if (m.ch === 'telemetry') useRobot.getState().setTelemetry(m.data)
          this.wanted.get(m.ch)?.forEach((fn) => fn(m.data))
          break
        case 'pong':
          useRobot.getState().setLatency(Math.round(performance.now() - m.t))
          break
        case 'hello':
          useTeleop.getState().setClientId(m.id)
          useTeleop.getState().setAuthenticated(!!m.authenticated)
          break
        case 'lease':
          useTeleop.getState().setLeaseHolder(m.holder)
          break
        case 'estop':
          useTeleop.getState().setEstopActive(m.active)
          break
        case 'err':
          console.warn('[ws] error', m.code, m.detail)
          break
      }
    }

    this.sock.onclose = () => {
      window.clearInterval(this.pingTimer)
      useRobot.getState().setStatus('offline')
      window.setTimeout(() => this.connect(), this.retry)
      this.retry = Math.min(this.retry * 2, 8000)
    }
    this.sock.onerror = () => this.sock?.close()
  }

  private send(obj: object) {
    if (this.sock?.readyState === WebSocket.OPEN) this.sock.send(JSON.stringify(obj))
  }

  /** Subscribe a listener to a channel; returns an unsubscribe fn. */
  on(channel: string, fn: Listener): () => void {
    let set = this.wanted.get(channel)
    if (!set) {
      set = new Set()
      this.wanted.set(channel, set)
      this.send({ op: 'sub', ch: channel })
    }
    set.add(fn)
    return () => {
      set!.delete(fn)
      if (set!.size === 0) {
        this.wanted.delete(channel)
        this.send({ op: 'unsub', ch: channel })
      }
    }
  }

  // ---- auth -----------------------------------------------------------------
  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY)
  }

  /** Store the control token and reconnect so the server re-evaluates auth. */
  setToken(token: string) {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
    this.sock?.close() // onclose triggers an immediate reconnect with the new token
  }

  // ---- teleop / safety (Phase 2) ----------------------------------------------
  sendTeleop(lin: number, ang: number, deadman: boolean) {
    this.send({ op: 'teleop', lin, ang, deadman })
  }

  sendEstop() {
    this.send({ op: 'estop' })
  }

  sendEstopRelease() {
    this.send({ op: 'estop_release' })
  }

  releaseControl() {
    this.send({ op: 'release_control' })
  }

  // ---- mode arbiter / skills (Phases 1-8) -------------------------------------
  setMode(mode: string) {
    this.send({ op: 'set_mode', mode })
  }

  runSkill(skill: string, args: string[] = []) {
    this.send({ op: 'run_skill', skill, args })
  }

  cancelSkill() {
    this.send({ op: 'cancel_skill' })
  }
}

export const ws = new WsClient()
