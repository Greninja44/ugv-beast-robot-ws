export interface ScanData {
  amin: number
  ainc: number
  rmax: number
  ranges: number[] // millimetres, 0 = invalid/out-of-range
}

export interface ImuData {
  ax: number; ay: number; az: number
  gx: number; gy: number; gz: number
  qw: number; qx: number; qy: number; qz: number
  yaw: number // radians, derived from the quaternion
}

export interface OdomData {
  x: number; y: number; yaw: number
  lin: number; ang: number
}

export interface TfFrame {
  ok: boolean
  age: number | null
}

export type TfData = Record<string, TfFrame>

export interface LogEntry {
  lvl: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'FATAL' | string
  node: string
  msg: string
  ts: number // unix seconds
}

export interface NavState {
  status: 'idle' | 'navigating' | 'succeeded' | 'canceled' | 'aborted' | 'rejected' | 'error' | string
  distance_remaining: number | null
  detail?: string
}

export interface MapMeta {
  width: number
  height: number
  resolution: number
  originX: number
  originY: number
}

export interface Waypoint {
  id: string
  name: string
  x: number
  y: number
  yaw: number
}

// robot_skills.mode_server — who currently holds motion authority.
export type RobotMode = 'idle' | 'teleop' | 'explore' | 'track' | 'ai' | string

export interface PerceptEntry {
  label: string
  confidence: number
  bearing: number // radians, + = left of camera center
  frame_id: string
  ts: number // unix seconds
  bbox: [number, number, number, number] // normalized [x, y, w, h]; all-zero = no box
}

export interface SkillState {
  skill: string | null
  status: 'idle' | 'running' | 'succeeded' | 'canceled' | 'aborted' | 'rejected' | 'error' | string
  feedback: string | null
  progress: number | null
  result_detail: string | null
}
