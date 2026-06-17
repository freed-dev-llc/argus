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

export interface DriftResponse {
  summary?: { total: number; dry_run: boolean }
  notes?: string[]
  error?: string
}

export function getDrift(): Promise<DriftResponse> {
  return getJSON<DriftResponse>('/api/drift')
}

export interface HealthResponse {
  status: string
  netbox_configured?: boolean
}

export function getHealth(): Promise<HealthResponse> {
  return getJSON<HealthResponse>('/health/deep')
}
