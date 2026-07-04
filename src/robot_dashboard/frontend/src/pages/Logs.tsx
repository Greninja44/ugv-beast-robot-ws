import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Download, Pause, Play, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import { ws } from '../lib/ws'
import { GlassCard } from '../components/GlassCard'
import type { LogEntry } from '../lib/sensorTypes'

const MAX_LOGS = 3000
const FLUSH_MS = 300

const LEVELS = ['DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL'] as const
type Level = (typeof LEVELS)[number]
const LEVEL_RANK: Record<string, number> = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3, FATAL: 4 }

const LEVEL_STYLE: Record<string, string> = {
  DEBUG: 'text-ink-dim',
  INFO: 'text-ink',
  WARN: 'text-warn',
  ERROR: 'text-bad',
  FATAL: 'text-bad font-bold',
}

export default function Logs() {
  const allLogs = useRef<LogEntry[]>([])
  const [displayLogs, setDisplayLogs] = useState<LogEntry[]>([])
  const [paused, setPaused] = useState(false)
  const [minLevel, setMinLevel] = useState<Level>('DEBUG')
  const [query, setQuery] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  const pausedRef = useRef(paused)
  pausedRef.current = paused

  // Effect runs once (empty deps) so pausing doesn't unsub/resub the WS channel
  // on every toggle — pausedRef is checked live inside the callback instead.
  useEffect(() => ws.on('log', (data) => {
    if (pausedRef.current) return
    const entries = data as LogEntry[]
    allLogs.current.push(...entries)
    if (allLogs.current.length > MAX_LOGS) {
      allLogs.current.splice(0, allLogs.current.length - MAX_LOGS)
    }
  }), [])

  // Batch React updates instead of re-rendering on every incoming message —
  // /rosout can be chatty, and a rolling log list re-rendering per-message
  // would jank the page for no visible benefit at human reading speed.
  useEffect(() => {
    const id = window.setInterval(() => setDisplayLogs([...allLogs.current]), FLUSH_MS)
    return () => window.clearInterval(id)
  }, [])

  const filtered = displayLogs.filter((e) => {
    if ((LEVEL_RANK[e.lvl] ?? 1) < LEVEL_RANK[minLevel]) return false
    if (query && !e.msg.toLowerCase().includes(query.toLowerCase()) &&
        !e.node.toLowerCase().includes(query.toLowerCase())) return false
    return true
  })

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [filtered.length, autoScroll])

  const clearLogs = () => {
    allLogs.current = []
    setDisplayLogs([])
  }

  const exportLogs = () => {
    const text = filtered
      .map((e) => `[${new Date(e.ts * 1000).toISOString()}] ${e.lvl.padEnd(5)} ${e.node}: ${e.msg}`)
      .join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ros-logs-${new Date().toISOString().replace(/[:.]/g, '-')}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
      className="flex flex-col gap-4 p-4"
    >
      <GlassCard className="sticky top-0 z-10 flex flex-wrap items-center gap-3">
        <select
          value={minLevel}
          onChange={(e) => setMinLevel(e.target.value as Level)}
          className="rounded-lg border border-edge bg-white/5 px-2.5 py-1.5 text-xs outline-none focus:border-accent"
        >
          {LEVELS.map((l) => <option key={l} value={l}>{l}+</option>)}
        </select>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="filter by message or node…"
          className="min-w-[200px] flex-1 rounded-lg border border-edge bg-white/5 px-3 py-1.5 text-xs
                     outline-none focus:border-accent"
        />

        <label className="flex items-center gap-1.5 text-xs text-ink-dim">
          <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />
          Auto-scroll
        </label>

        <button onClick={() => setPaused((p) => !p)}
                className="flex items-center gap-1.5 rounded-lg border border-edge px-2.5 py-1.5 text-xs
                           text-ink-dim hover:text-ink transition-colors">
          {paused ? <Play size={14} /> : <Pause size={14} />} {paused ? 'Resume' : 'Pause'}
        </button>
        <button onClick={exportLogs}
                className="flex items-center gap-1.5 rounded-lg border border-edge px-2.5 py-1.5 text-xs
                           text-ink-dim hover:text-ink transition-colors">
          <Download size={14} /> Export
        </button>
        <button onClick={clearLogs}
                className="flex items-center gap-1.5 rounded-lg border border-edge px-2.5 py-1.5 text-xs
                           text-ink-dim hover:text-ink transition-colors">
          <Trash2 size={14} /> Clear
        </button>

        <span className="ml-auto text-[11px] text-ink-dim">{filtered.length} / {displayLogs.length}</span>
      </GlassCard>

      <GlassCard className="!p-3 font-mono text-[12px] leading-relaxed">
        {filtered.length === 0 && (
          <p className="p-4 text-center text-ink-dim">
            {displayLogs.length === 0 ? 'waiting for /rosout…' : 'no entries match the current filter'}
          </p>
        )}
        {filtered.map((e, i) => (
          <div key={i} className="flex gap-2 whitespace-pre-wrap border-b border-white/5 py-1">
            <span className="shrink-0 text-ink-dim">
              {new Date(e.ts * 1000).toLocaleTimeString()}
            </span>
            <span className={clsx('shrink-0 w-12', LEVEL_STYLE[e.lvl] ?? 'text-ink')}>{e.lvl}</span>
            <span className="shrink-0 text-ink-dim">{e.node}</span>
            <span className="text-ink">{e.msg}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </GlassCard>
    </motion.div>
  )
}
