import { ws } from './ws'

/** Fetch wrapper that attaches the control token as a Bearer header for REST calls
 * that mutate robot state (limits, e-stop). Read-only GETs don't need it. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = ws.getToken()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  return fetch(`/api${path}`, { ...init, headers })
}
