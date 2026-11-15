import type { MultiPolygon, Polygon } from 'geojson'

export type LngLat = [number, number]

export type ShapeKind = 'polygon' | 'rectangle' | 'region'
export type DrawMode = ShapeKind

export type RegionGeometry = Polygon | MultiPolygon

export interface AoiPolygon {
  id: string
  name: string
  kind: ShapeKind
  coords: LngLat[] // open ring (first vertex is not repeated); empty for regions
  geometry?: RegionGeometry // administrative boundary, only for kind 'region'
}

// Backend responses (backend/app/schemas.py); only the fields the UI reads.
export interface EstimateResult {
  area_km2: number
  total_bytes: number
  human: string
  assumptions: string
}

export interface SearchResult {
  inventory_id: string
  products: { product_id: string }[]
}

export type JobState = 'queued' | 'running' | 'done' | 'failed'

export interface JobResult {
  product_id: string
  state: string // 'downloaded' on success, 'error' otherwise
  error?: string
}

export interface Job {
  id: string
  state: JobState
  results: JobResult[]
  error: string | null
  files: string[] // download order; file i is served at /api/jobs/{id}/files/{i}
}
