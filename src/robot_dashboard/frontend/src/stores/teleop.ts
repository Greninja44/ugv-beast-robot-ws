import { create } from 'zustand'

interface Limits {
  max_linear: number
  max_angular: number
  limit_linear: number
  limit_angular: number
}

interface TeleopState {
  clientId: string | null
  authenticated: boolean
  leaseHolder: string | null
  estopActive: boolean
  limits: Limits | null
  setClientId: (id: string) => void
  setAuthenticated: (a: boolean) => void
  setLeaseHolder: (h: string | null) => void
  setEstopActive: (a: boolean) => void
  setLimits: (l: Limits) => void
}

export const useTeleop = create<TeleopState>((set) => ({
  clientId: null,
  authenticated: false,
  leaseHolder: null,
  estopActive: false,
  limits: null,
  setClientId: (clientId) => set({ clientId }),
  setAuthenticated: (authenticated) => set({ authenticated }),
  setLeaseHolder: (leaseHolder) => set({ leaseHolder }),
  setEstopActive: (estopActive) => set({ estopActive }),
  setLimits: (limits) => set({ limits }),
}))
