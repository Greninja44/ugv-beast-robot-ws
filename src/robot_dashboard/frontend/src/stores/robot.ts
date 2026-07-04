import { create } from 'zustand'

export type ConnStatus = 'connecting' | 'online' | 'offline'

export interface Telemetry {
  ros: boolean
  nodes: number
  topics: number
  voltage: number | null
  pct: number | null
  low_batt: boolean
  lin: number | null
  ang: number | null
  pose: { x: number; y: number; yaw: number } | null
  loc: string
  cpu: number
  mem: number
  temp: number | null
}

interface RobotState {
  status: ConnStatus
  latencyMs: number | null
  telemetry: Telemetry | null
  setStatus: (s: ConnStatus) => void
  setLatency: (ms: number) => void
  setTelemetry: (t: Telemetry) => void
}

export const useRobot = create<RobotState>((set) => ({
  status: 'connecting',
  latencyMs: null,
  telemetry: null,
  setStatus: (status) => set({ status }),
  setLatency: (latencyMs) => set({ latencyMs }),
  setTelemetry: (telemetry) => set({ telemetry }),
}))
