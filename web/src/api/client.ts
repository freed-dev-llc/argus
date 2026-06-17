// Thin client for the Argus FastAPI server.
// In dev, requests are proxied to :8080 (see vite.config.ts). In production, set
// VITE_ARGUS_API to the server's base URL.

const BASE = import.meta.env.VITE_ARGUS_API ?? ''

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`)
  }
  return (await res.json()) as T
}

async function postJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'POST' })
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`)
  }
  return (await res.json()) as T
}

export interface Device {
  id?: number
  name?: string
  status?: unknown
  site?: unknown
  [key: string]: unknown
}

export interface DevicesResponse {
  devices?: Device[]
  count?: number
  error?: string
}

export function getDevices(): Promise<DevicesResponse> {
  return getJSON<DevicesResponse>('/api/devices')
}

export interface Change {
  action: string
  object_type: string
  identifier: string
  details: Record<string, unknown>
}

export interface PlanSummary {
  total: number
  by_action?: Record<string, number>
  dry_run: boolean
}

export interface DriftResponse {
  collector?: string
  summary?: PlanSummary
  changes?: Change[]
  notes?: string[]
  error?: string
}

export function getDrift(collector = 'unifi'): Promise<DriftResponse> {
  return getJSON<DriftResponse>(`/api/drift?collector=${encodeURIComponent(collector)}`)
}

export interface ChangeResult {
  action: string
  identifier: string
  status: string
  detail?: unknown
}

export interface ReconcileResponse {
  // confirmation step
  confirmation_required?: boolean
  confirm_token?: string
  expires_at?: string
  summary?: PlanSummary
  changes?: Change[]
  message?: string
  // applied step
  confirmed?: boolean
  applied?: boolean
  applied_count?: number
  results?: ChangeResult[]
  notes?: string[]
  error?: string
}

export function postReconcile(confirmToken?: string, collector = 'unifi'): Promise<ReconcileResponse> {
  const params = new URLSearchParams({ collector })
  if (confirmToken) params.set('confirm_token', confirmToken)
  return postJSON<ReconcileResponse>(`/api/reconcile?${params.toString()}`)
}

export interface HealthResponse {
  status: string
  netbox_configured?: boolean
}

export function getHealth(): Promise<HealthResponse> {
  return getJSON<HealthResponse>('/health/deep')
}
