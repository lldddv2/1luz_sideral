import type { EstimateResult, Job, SearchResult } from './types'

// Mirrors max_results in backend/app/services/nisar.py (search): the most products one search returns.
export const MAX_SEARCH_PRODUCTS = 10
export const DEFAULT_START = '2025-08-01'
export const ESTIMATE_DEBOUNCE_MS = 400
export const POLL_MS = 5000

// Yellow warnings only: they never disable the download button. Bytes are binary, like the backend `human`.
const MB = 1024 * 1024
export const DOWNLOAD_LIMITS = {
  totalBytes: 500 * MB,
  areaKm2: 2500,
}

export type Pol = 'HH' | 'HV'
export const POLS: Pol[] = ['HH', 'HV']
export const POL_VARIABLE: Record<Pol, string> = {
  HH: '/science/LSAR/GCOV/grids/frequencyA/HHHH',
  HV: '/science/LSAR/GCOV/grids/frequencyA/HVHV',
}

// Local calendar date as YYYY-MM-DD, the format of <input type="date">.
export function todayIso(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function messageOf(err: unknown): string {
  if (err instanceof TypeError) return 'Sin conexión con el backend'
  return err instanceof Error ? err.message : String(err)
}

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // Not JSON: fall through to the status code.
  }
  return `HTTP ${res.status}`
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) throw new Error(await errorText(res))
  return (await res.json()) as T
}

function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return call<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}

export interface EstimateBody {
  geometry: unknown
  variables: number
  inventory_id?: string // sizes the products of a search; without it the estimate covers one product
}

export const fetchEstimate = (body: EstimateBody, signal?: AbortSignal) =>
  postJson<EstimateResult>('/api/estimate', body, signal)

// start and end are full ISO timestamps with timezone, as the backend requires.
export const searchProducts = (geometry: unknown, start: string, end: string) =>
  postJson<SearchResult>('/api/search', { geometry, start, end })

export const createJob = (inventoryId: string, productIds: string[], variables: string[]) =>
  postJson<Job>('/api/jobs', { inventory_id: inventoryId, product_ids: productIds, variables })

export const fetchJob = (id: string) => call<Job>(`/api/jobs/${encodeURIComponent(id)}`)

export const fileUrl = (jobId: string, index: number) =>
  `/api/jobs/${encodeURIComponent(jobId)}/files/${index}`

// Warning lines for every limit an estimate exceeds.
export function warningsFor(e: EstimateResult): string[] {
  const out: string[] = []
  if (e.total_bytes > DOWNLOAD_LIMITS.totalBytes) out.push(`Descarga mayor a ${DOWNLOAD_LIMITS.totalBytes / MB} MB`)
  if (e.area_km2 > DOWNLOAD_LIMITS.areaKm2) out.push(`Área mayor a ${DOWNLOAD_LIMITS.areaKm2} km²`)
  return out
}

export function formatKm2(value: number): string {
  return `${value < 10 ? value.toFixed(2) : Math.round(value)} km²`
}
