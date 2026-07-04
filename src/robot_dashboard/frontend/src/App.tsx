import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import StatusStrip from './components/StatusStrip'
import Dashboard from './pages/Dashboard'
import Teleop from './pages/Teleop'
import Sensors from './pages/Sensors'
import Logs from './pages/Logs'
import Controls from './pages/Controls'
import Settings from './pages/Settings'
import Nav from './pages/Nav'
import { ws } from './lib/ws'
import { useRobot } from './stores/robot'
import { useTeleop } from './stores/teleop'

export default function App() {
  // Connect once; keep the telemetry channel alive app-wide (it feeds the status strip).
  useEffect(() => {
    ws.connect()
    return ws.on('telemetry', () => {})
  }, [])

  const status = useRobot((s) => s.status)
  const estopActive = useTeleop((s) => s.estopActive)

  return (
    <div className="flex h-full flex-col md:flex-row">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col pb-14 md:pb-0">
        <StatusStrip />
        {status === 'offline' && (
          <div className="bg-bad/15 px-4 py-1.5 text-center text-xs text-bad">
            Connection lost — reconnecting…
          </div>
        )}
        {estopActive && (
          <div className="bg-bad/20 px-4 py-1.5 text-center text-xs font-semibold text-bad">
            EMERGENCY STOP ACTIVE — all motion commands are being rejected
          </div>
        )}
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            {/* Camera merged into Manual Control (FPV-style: drive while watching the feed) */}
            <Route path="/camera" element={<Navigate to="/teleop" replace />} />
            <Route path="/teleop" element={<Teleop />} />
            <Route path="/sensors" element={<Sensors />} />
            <Route path="/nav" element={<Nav />} />
            <Route path="/controls" element={<Controls />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
