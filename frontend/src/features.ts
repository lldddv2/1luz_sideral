import type { BBox } from './nominatim'
import { inPolygon } from './geo'
import type { AoiPolygon, RegionGeometry } from './types'

// Global catalog of named natural features served by the backend (/api/features).
export interface NaturalFeature {
  id: string
  name: string
  category: string // desert, wetland, glacier, forest, jungle, mangrove, tundra, volcano
  category_name: string // Spanish label, e.g. "Humedal"
  lon: number
  lat: number
  bbox: BBox
}

// Plural Spanish labels for the "show all" row and the map chip.
export const CATEGORY_PLURAL: Record<string, string> = {
  desert: 'Desiertos',
  wetland: 'Humedales',
  glacier: 'Glaciares',
  forest: 'Bosques',
  jungle: 'Selvas',
  mangrove: 'Manglares',
  tundra: 'Tundras',
  volcano: 'Volcanes',
}

export const CATEGORY_COLOR: Record<string, string> = {
  desert: '#d97706',
  wetland: '#0891b2',
  glacier: '#38bdf8',
  forest: '#15803d',
  jungle: '#166534',
  mangrove: '#0d9488',
  tundra: '#7c8a9a',
  volcano: '#dc2626',
}

// Same-origin like the rest of the API (Vite proxies /api in dev).
// With areas, the backend keeps only features whose simplified outline meets one of them.
export async function fetchFeatures(q: string, areas: RegionGeometry[] = [], signal?: AbortSignal): Promise<NaturalFeature[]> {
  const res = await fetch('/api/features/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ q, areas }),
    signal,
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as NaturalFeature[]
}

// Simplified outline of one feature (lists leave it out to stay light). Cached per id.
const outlines = new Map<string, Promise<RegionGeometry>>()
export function fetchOutline(id: string): Promise<RegionGeometry> {
  let p = outlines.get(id)
  if (!p) {
    p = fetch(`/api/features/${encodeURIComponent(id)}`).then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return ((await res.json()) as { geometry: RegionGeometry }).geometry
    })
    p.catch(() => outlines.delete(id))
    outlines.set(id, p)
  }
  return p
}

// Each study area as GeoJSON (drawn shapes become a closed polygon ring).
export function aoiGeometries(polygons: AoiPolygon[]): RegionGeometry[] {
  return polygons.flatMap((p): RegionGeometry[] => {
    if (p.geometry) return [p.geometry]
    if (p.coords.length < 3) return []
    return [{ type: 'Polygon', coordinates: [[...p.coords, p.coords[0]]] }]
  })
}

// Chip and "show on map" label: the plural category name when all results share one category.
export function groupLabel(results: NaturalFeature[]): string {
  const cat = results[0]?.category
  return cat && results.every((f) => f.category === cat) ? CATEGORY_PLURAL[cat] ?? cat : 'Lugares naturales'
}

// Bounding box of each study area (drawn shape or region boundary).
export function aoiBoxes(polygons: AoiPolygon[]): BBox[] {
  const boxes: BBox[] = []
  for (const p of polygons) {
    const pts: number[][] = p.geometry
      ? p.geometry.type === 'Polygon'
        ? p.geometry.coordinates.flat()
        : p.geometry.coordinates.flat(2)
      : p.coords
    if (pts.length === 0) continue
    const xs = pts.map((c) => c[0])
    const ys = pts.map((c) => c[1])
    boxes.push([Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)])
  }
  return boxes
}

export function inBoxes(f: NaturalFeature, boxes: BBox[]): boolean {
  return boxes.some((b) => f.bbox[0] <= b[2] && b[0] <= f.bbox[2] && f.bbox[1] <= b[3] && b[1] <= f.bbox[3])
}

// Inside the outer ring and outside every hole, for Polygon and MultiPolygon.
export function pointInShapes(lon: number, lat: number, shapes: RegionGeometry[]): boolean {
  return shapes.some((g) =>
    g.type === 'Polygon'
      ? inPolygon(g.coordinates, [lon, lat])
      : g.coordinates.some((poly) => inPolygon(poly, [lon, lat])),
  )
}

// A natural feature meets a study area when its point lies inside the true shape, or when its
// bbox overlaps the shape (a bbox corner inside it, or a shape vertex inside the bbox).
export function inShapes(f: NaturalFeature, shapes: RegionGeometry[]): boolean {
  if (pointInShapes(f.lon, f.lat, shapes)) return true
  const [w, s, e, n] = f.bbox
  const corners: [number, number][] = [
    [w, s],
    [e, s],
    [e, n],
    [w, n],
  ]
  if (corners.some(([x, y]) => pointInShapes(x, y, shapes))) return true
  return shapes.some((g) => {
    const pts = g.type === 'Polygon' ? g.coordinates.flat() : g.coordinates.flat(2)
    return pts.some(([x, y]) => x >= w && x <= e && y >= s && y <= n)
  })
}
