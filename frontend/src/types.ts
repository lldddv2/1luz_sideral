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

// User-marked point of interest: a center with a square range around it (annotation only, not a study area).
export interface UserZone {
  id: string
  center: LngLat // [lon, lat], WGS84; the square is centered here
  halfSizeKm: number // half the side of the square, in km
  name?: string
  note?: string
}

// What the Descarga section downloads: the square of the selected point of interest.
export interface DownloadTarget {
  id: string // zone id
  name: string
  sideKm: number
  geometry: RegionGeometry
  outsideStudy: boolean // study areas exist and the square meets none of them
}

// Backend responses (backend/app/schemas.py); only the fields the UI reads.
export interface EstimateResult {
  area_km2: number
  total_bytes: number
  human: string
  assumptions: string
}

export type FlightDirection = 'ascending' | 'descending'

// One product found by search: its swath footprint and where it sits in the orbit.
export interface SearchProduct {
  product_id: string
  acquisition_start: string | null // UTC ISO, e.g. 2026-10-30T12:03:29Z
  geometry: RegionGeometry // swath footprint, WGS84
  track: number | null
  direction: FlightDirection | null
  frame: number | null
}

export interface SearchResult {
  inventory_id: string
  products: SearchProduct[]
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
