import type { LngLat, RegionGeometry } from './types'

// ESA WorldCover 2021 land cover, served by /api/landcover. The classes come from the backend; the Spanish
// synonyms below only map words typed in the search bar to class keys.

export interface LandcoverClass {
  code: number
  key: string // stable id, e.g. wetland; the backend filters by it
  name: string // Spanish label
  name_en: string // ESA legend label
  color: string // #rrggbb
}

export interface LandcoverClassStats extends LandcoverClass {
  pixels: number
  area_km2: number
  percent: number // share of total_km2, nodata excluded
}

export interface LandcoverStats {
  total_km2: number
  nodata_km2: number
  resolution_m: number
  classes: LandcoverClassStats[]
}

// Corners in MapLibre image source order: NW, NE, SE, SW.
export type Quad = [LngLat, LngLat, LngLat, LngLat]

export interface CoverMaskImage {
  url: string // data URL of the RGBA PNG
  bounds: Quad
}

// Stats of one area: request in flight, ready, or failed.
export type StatsEntry =
  | { status: 'loading' }
  | { status: 'ready'; stats: LandcoverStats }
  | { status: 'error'; message: string }

// One class of the active filter. percent stays null until the stats of the active area are ready.
export interface CoverChip {
  key: string
  name: string
  color: string
  percent: number | null
}

// What the search bar needs to offer land cover: the class table, the filter and the active area.
export interface CoverSuggestions {
  classes: LandcoverClass[] // backend order; empty until loaded
  classesError: string | null
  filter: string[] // class keys of the chips
  area: { name: string; stats: StatsEntry | undefined } | null // null when no area is active
}

// Spanish words per class key, as typed in the search bar. Plural forms are listed because a prefix
// match needs the full word once the user has typed it.
export const SYNONYMS: Record<string, string[]> = {
  wetland: ['humedal', 'humedales', 'pantano', 'ciénaga', 'turbera', 'marisma'],
  tree: ['bosque', 'bosques', 'selva', 'árboles', 'forestal'],
  snow_ice: ['glaciar', 'glaciares', 'hielo', 'nieve'],
  water: ['agua', 'lago', 'laguna', 'río', 'embalse'],
  cropland: ['cultivo', 'cultivos', 'agrícola', 'agricultura'],
  built_up: ['urbano', 'ciudad', 'construido'],
  mangrove: ['manglar', 'manglares'],
  grassland: ['pastizal', 'pradera', 'pasto'],
  shrubland: ['matorral', 'arbustos'],
  bare: ['desierto', 'suelo desnudo', 'árido'],
  moss: ['musgo', 'liquen', 'tundra'],
}

// Lowercase without accents: 'Ciénaga' becomes 'cienaga'.
const fold = (text: string) => text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()

// Keys of the classes a query names, in table order. A term matches when the query starts it or starts one of
// its words, so "desnudo" finds bare. Queries under two letters match nothing.
export function matchCover(query: string): string[] {
  const q = fold(query).trim()
  if (q.length < 2) return []
  return Object.entries(SYNONYMS)
    .filter(([, terms]) =>
      terms.some((term) => {
        const t = fold(term)
        return t.startsWith(q) || t.split(' ').some((word) => word.startsWith(q))
      }),
    )
    .map(([key]) => key)
}

const PERCENT = new Intl.NumberFormat('es', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

// Spanish decimal comma, e.g. 12,4 %.
export const formatPercent = (value: number) => (value > 0 && value < 0.1 ? '< 0,1 %' : `${PERCENT.format(value)} %`)

// The backend detail is English and only the status matters here, so errors are worded in Spanish by status.
const ERROR_TEXT: Record<number, string> = {
  422: 'Área no válida o demasiado grande.',
  502: 'No se pudo leer la cobertura WorldCover.',
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) throw new Error(ERROR_TEXT[res.status] ?? `HTTP ${res.status}`)
  return (await res.json()) as T
}

const postJson = <T>(path: string, body: unknown, signal?: AbortSignal) =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })

export const fetchClasses = (signal?: AbortSignal) => request<LandcoverClass[]>('/api/landcover/classes', { signal })

export const fetchStats = (geometry: RegionGeometry, signal?: AbortSignal) =>
  postJson<LandcoverStats>('/api/landcover/stats', { geometry }, signal)

// Mask of the given class keys over the geometry, as an image source for the map.
export async function fetchMask(
  geometry: RegionGeometry,
  classes: string[],
  signal?: AbortSignal,
): Promise<CoverMaskImage> {
  const mask = await postJson<{ bounds: Quad; png_base64: string }>(
    '/api/landcover/mask',
    { geometry, classes },
    signal,
  )
  return { url: `data:image/png;base64,${mask.png_base64}`, bounds: mask.bounds }
}
