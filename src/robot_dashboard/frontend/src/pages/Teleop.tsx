import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Camera as CameraIcon, Circle, Download, Gamepad2, Keyboard, Lightbulb, Maximize,
  OctagonX, PlayCircle, ShieldAlert, Square, Unlock,
} from 'lucide-react'
import { ws } from '../lib/ws'
import { apiFetch } from '../lib/api'
import { useTeleop } from '../stores/teleop'
import { Joystick } from '../components/Joystick'
import { GlassCard } from '../components/GlassCard'
import { useKeyboardTeleop } from '../features/teleop/useKeyboardTeleop'
import { useGamepadTeleop } from '../features/teleop/useGamepadTeleop'

const SAMPLE_HZ = 15

interface StreamInfo { id: string; name: string; topic: string }

function TokenGate() {
  const [value, setValue] = useState('')
  return (
    <GlassCard title="Unlock control" className="max-w-md">
      <p className="mb-3 text-sm text-ink-dim">
        This dashboard boots in read-only mode. Enter the control token configured in{' '}
        <code>robot_dashboard/config/dashboard.yaml</code> to enable driving.
      </p>
      <div className="flex gap-2">
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="control token"
          className="flex-1 rounded-lg border border-edge bg-white/5 px-3 py-2 text-sm
                     outline-none focus:border-accent"
        />
        <button
          onClick={() => ws.setToken(value)}
          className="rounded-lg bg-accent/20 px-4 py-2 text-sm font-medium text-accent
                     hover:bg-accent/30 transition-colors"
        >
          Unlock
        </button>
      </div>
    </GlassCard>
  )
}

/** Live camera view with fullscreen/snapshot/record — same feature set as the
 * old standalone Camera page, now docked next to the drive controls so you can
 * watch the feed while driving (FPV-style), which is the whole point of having
 * both on one page. */
function CameraPanel() {
  const containerRef = useRef<HTMLDivElement>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const drawTimerRef = useRef<number | undefined>(undefined)

  const [streams, setStreams] = useState<StreamInfo[]>([])
  const [selected, setSelected] = useState<string>('')
  const [streaming, setStreaming] = useState(true)
  const [recording, setRecording] = useState(false)
  const [imgError, setImgError] = useState(false)
  const [frameLoaded, setFrameLoaded] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    fetch('/api/camera/streams').then((r) => r.json()).then((list: StreamInfo[]) => {
      setStreams(list)
      if (list.length > 0) setSelected(list[0].id)
    }).catch(() => {})
  }, [])

  // A multipart stream can connect fine (200 OK) and just never deliver a first
  // frame (e.g. the camera driver isn't publishing) — that never fires the
  // <img> error event, only a hard connection failure would. So: no successful
  // frame within a few seconds is ALSO treated as unavailable; onLoad below
  // clears it as soon as the first real JPEG part actually renders.
  useEffect(() => {
    if (!streaming || imgError || frameLoaded) return
    const timer = window.setTimeout(() => setImgError(true), 6000)
    return () => window.clearTimeout(timer)
  }, [streaming, imgError, frameLoaded, reloadKey])

  const retry = () => {
    setImgError(false)
    setFrameLoaded(false)
    setReloadKey((k) => k + 1)
  }

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) containerRef.current?.requestFullscreen()
    else document.exitFullscreen()
  }

  const takeSnapshot = async () => {
    const r = await fetch('/api/camera/snapshot')
    if (!r.ok) return
    const blob = await r.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `snapshot-${new Date().toISOString().replace(/[:.]/g, '-')}.jpg`
    a.click()
    URL.revokeObjectURL(url)
  }

  const startRecording = () => {
    const img = imgRef.current
    const canvas = canvasRef.current
    if (!img || !canvas) return
    const w = img.naturalWidth || 640, h = img.naturalHeight || 480
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')!

    // MJPEG <img> can't be captured directly — mirror its current bitmap onto a
    // canvas on a timer, then capture THAT canvas's stream for MediaRecorder.
    drawTimerRef.current = window.setInterval(() => {
      try { ctx.drawImage(img, 0, 0, w, h) } catch { /* frame not ready yet */ }
    }, 1000 / 15)

    const stream = canvas.captureStream(15)
    const recorder = new MediaRecorder(stream, { mimeType: 'video/webm' })
    const chunks: BlobPart[] = []
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: 'video/webm' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `recording-${new Date().toISOString().replace(/[:.]/g, '-')}.webm`
      a.click()
      URL.revokeObjectURL(url)
    }
    recorder.start()
    recorderRef.current = recorder
    setRecording(true)
  }

  const stopRecording = () => {
    recorderRef.current?.stop()
    recorderRef.current = null
    window.clearInterval(drawTimerRef.current)
    setRecording(false)
  }

  useEffect(() => () => {
    window.clearInterval(drawTimerRef.current)
    recorderRef.current?.stop()
  }, [])

  return (
    <GlassCard className="xl:col-span-3 !p-0 overflow-hidden">
      <div ref={containerRef} className="relative bg-black flex items-center justify-center aspect-video">
        {streaming && !imgError ? (
          <img
            key={reloadKey}
            ref={imgRef}
            src="/api/camera/stream"
            alt="Robot camera feed"
            className="max-h-full max-w-full"
            onLoad={() => setFrameLoaded(true)}
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex flex-col items-center gap-3 text-ink-dim">
            <CameraIcon size={40} strokeWidth={1.2} />
            <p className="text-sm">
              {imgError ? 'Camera feed unavailable — is the OAK-D connected?' : 'Stream paused'}
            </p>
            {imgError && (
              <button onClick={retry}
                      className="rounded-lg bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent
                                 hover:bg-accent/25 transition-colors">
                Retry
              </button>
            )}
          </div>
        )}

        {recording && (
          <span className="absolute top-3 left-3 flex items-center gap-1.5 rounded-full bg-bad/80
                           px-2.5 py-1 text-xs font-semibold text-white">
            <Circle size={8} className="fill-white animate-pulse" /> REC
          </span>
        )}

        <div className="absolute top-3 right-3 flex items-center gap-2">
          {streams.length > 1 && (
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="rounded-lg bg-black/50 px-2 py-1.5 text-xs text-white backdrop-blur outline-none"
            >
              {streams.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
        </div>

        <div className="absolute bottom-3 right-3 flex items-center gap-2">
          <button onClick={() => setStreaming((s) => !s)} title={streaming ? 'Pause stream' : 'Resume stream'}
                  className="rounded-lg bg-black/50 p-2 text-white backdrop-blur hover:bg-black/70 transition-colors">
            {streaming ? <Square size={16} /> : <PlayCircle size={16} />}
          </button>
          <button onClick={takeSnapshot} title="Screenshot"
                  className="rounded-lg bg-black/50 p-2 text-white backdrop-blur hover:bg-black/70 transition-colors">
            <Download size={16} />
          </button>
          <button onClick={recording ? stopRecording : startRecording}
                  title={recording ? 'Stop recording' : 'Start recording'}
                  className="rounded-lg bg-black/50 p-2 text-white backdrop-blur hover:bg-black/70 transition-colors">
            {recording ? <Square size={16} /> : <Circle size={16} />}
          </button>
          <button onClick={toggleFullscreen} title="Fullscreen"
                  className="rounded-lg bg-black/50 p-2 text-white backdrop-blur hover:bg-black/70 transition-colors">
            <Maximize size={16} />
          </button>
        </div>
      </div>
      <canvas ref={canvasRef} className="hidden" />
    </GlassCard>
  )
}

export default function Teleop() {
  const { authenticated, clientId, leaseHolder, estopActive, limits, setLimits } = useTeleop()
  const youHaveControl = leaseHolder !== null && leaseHolder === clientId
  const someoneElseHasControl = leaseHolder !== null && leaseHolder !== clientId

  const latest = useRef({ lin: 0, ang: 0, deadman: false })
  const setInput = useCallback((lin: number, ang: number, deadman: boolean) => {
    latest.current = { lin, ang, deadman }
    ws.sendTeleop(lin, ang, deadman)
  }, [])

  const canDrive = authenticated && !estopActive && !someoneElseHasControl
  const canDriveRef = useRef(canDrive)
  canDriveRef.current = canDrive

  // Keep-alive sampler: while deadman is held, resend at SAMPLE_HZ so the server's
  // watchdog (300ms) never sees a gap even if the input source itself is idle. Also
  // guards against a stale "held" joystick/key state outliving a permission change
  // (e-stop engaged, lease lost mid-drive) — canDriveRef is checked every tick.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (!canDriveRef.current) return
      if (latest.current.deadman) ws.sendTeleop(latest.current.lin, latest.current.ang, true)
    }, 1000 / SAMPLE_HZ)
    return () => window.clearInterval(id)
  }, [])

  // The moment driving becomes disallowed, force an immediate stop regardless of
  // what any input source's internal (pointer-down / key-held) state still thinks.
  useEffect(() => {
    if (!canDrive && latest.current.deadman) {
      latest.current = { lin: 0, ang: 0, deadman: false }
      ws.sendTeleop(0, 0, false)
    }
  }, [canDrive])

  useKeyboardTeleop(canDrive, setInput)
  useGamepadTeleop(canDrive, setInput)

  // Fetch speed limits once authenticated.
  useEffect(() => {
    if (!authenticated) return
    apiFetch('/teleop/limits').then((r) => r.json()).then(setLimits).catch(() => {})
  }, [authenticated, setLimits])

  const updateLimit = async (key: 'linear' | 'angular', value: number) => {
    const r = await apiFetch('/teleop/limits', { method: 'PUT', body: JSON.stringify({ [key]: value }) })
    if (r.ok) setLimits(await r.json())
  }

  const toggleEstop = () => (estopActive ? ws.sendEstopRelease() : ws.sendEstop())

  const [ledOn, setLedOn] = useState(false)
  useEffect(() => {
    fetch('/api/controls/led').then((r) => r.json()).then((d) => setLedOn(d.on)).catch(() => {})
  }, [])
  const toggleLed = async () => {
    const r = await apiFetch('/controls/led', { method: 'PUT', body: JSON.stringify({ on: !ledOn }) })
    if (r.ok) setLedOn((await r.json()).on)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
      className="grid gap-4 p-4 md:grid-cols-2 xl:grid-cols-4"
    >
      {!authenticated && <TokenGate />}

      {authenticated && (
        <>
          <CameraPanel />

          <GlassCard title="Control status">
            <div className="flex items-center gap-2 text-sm">
              {estopActive ? (
                <span className="flex items-center gap-1.5 text-bad"><ShieldAlert size={16} /> E-STOP ACTIVE</span>
              ) : youHaveControl ? (
                <span className="flex items-center gap-1.5 text-good"><Unlock size={16} /> You have control</span>
              ) : someoneElseHasControl ? (
                <span className="text-warn">Another client is driving</span>
              ) : (
                <span className="text-ink-dim">No one is driving</span>
              )}
            </div>
            <button
              onClick={toggleEstop}
              className={`mt-4 flex w-full items-center justify-center gap-2 rounded-xl py-3 font-bold
                         transition-colors ${estopActive
                ? 'bg-good/15 text-good hover:bg-good/25'
                : 'bg-bad/15 text-bad hover:bg-bad/25'}`}
            >
              {estopActive ? <PlayCircle size={18} /> : <OctagonX size={18} />}
              {estopActive ? 'RESUME' : 'EMERGENCY STOP'}
            </button>
            {youHaveControl && (
              <button
                onClick={() => ws.releaseControl()}
                className="mt-2 w-full rounded-xl border border-edge py-2 text-xs text-ink-dim
                           hover:text-ink transition-colors"
              >
                Release control
              </button>
            )}
            <button
              onClick={toggleLed}
              className={`mt-2 flex w-full items-center justify-center gap-2 rounded-xl py-2.5
                         text-sm font-medium transition-colors ${ledOn
                ? 'bg-warn/15 text-warn hover:bg-warn/25'
                : 'border border-edge text-ink-dim hover:text-ink'}`}
            >
              <Lightbulb size={16} className={ledOn ? 'fill-warn' : ''} />
              {ledOn ? 'Lights ON' : 'Lights OFF'}
            </button>
          </GlassCard>

          <GlassCard title="Virtual joystick" className="flex flex-col items-center xl:col-span-2">
            <Joystick onInput={setInput} disabled={!canDrive} size={160} />
            <p className="mt-3 text-xs text-ink-dim">Touch and drag — release to stop instantly.</p>
          </GlassCard>

          <GlassCard title="Speed limiter">
            {limits && (
              <div className="space-y-4">
                <div>
                  <div className="mb-1 flex justify-between text-xs text-ink-dim">
                    <span>Linear</span><span>{limits.limit_linear.toFixed(2)} / {limits.max_linear.toFixed(2)} m/s</span>
                  </div>
                  <input
                    type="range" min={0} max={limits.max_linear} step={0.05}
                    value={limits.limit_linear}
                    onChange={(e) => updateLimit('linear', Number(e.target.value))}
                    className="w-full accent-accent"
                  />
                </div>
                <div>
                  <div className="mb-1 flex justify-between text-xs text-ink-dim">
                    <span>Angular</span><span>{limits.limit_angular.toFixed(2)} / {limits.max_angular.toFixed(2)} rad/s</span>
                  </div>
                  <input
                    type="range" min={0} max={limits.max_angular} step={0.05}
                    value={limits.limit_angular}
                    onChange={(e) => updateLimit('angular', Number(e.target.value))}
                    className="w-full accent-accent"
                  />
                </div>
              </div>
            )}
          </GlassCard>

          <GlassCard title="Input sources" className="text-xs text-ink-dim xl:col-span-2">
            <div className="flex items-center gap-2"><Keyboard size={14} /> WASD / Arrow keys — hold to drive</div>
            <div className="mt-1.5 flex items-center gap-2"><Gamepad2 size={14} /> Gamepad — hold a bumper/trigger</div>
            {someoneElseHasControl && (
              <p className="mt-3 text-warn">Input disabled: another client holds the lease.</p>
            )}
            {estopActive && <p className="mt-3 text-bad">Input disabled: e-stop is active.</p>}
          </GlassCard>
        </>
      )}
    </motion.div>
  )
}
