import type { RegionGeometry } from './types'

// Place and administrative region search (OpenStreetMap Nominatim through the backend).

// [west, south, east, north], the order used by fitBounds.
export type BBox = [number, number, number, number]

export interface PlaceResult {
  id: string
  name: string
  label: string // full display name, e.g. "Antioquia, Colombia"
  type: string // Spanish kind, e.g. "País" or "Departamento / Estado"
  bbox: BBox
  geometry: RegionGeometry | null // administrative boundary; null for points and lines
}

// Administrative regions (countries, states, municipalities, cities) via the backend proxy
// (/api/regions), which rate-limits and caches Nominatim and returns simplified outlines.
// With a viewbox, Nominatim only returns places inside it (bounded=1 on the backend).
export async function searchPlaces(q: string, signal?: AbortSignal, viewbox?: BBox): Promise<PlaceResult[]> {
  const params = new URLSearchParams({ q })
  if (viewbox) params.set('viewbox', viewbox.map((v) => v.toFixed(5)).join(','))
  const res = await fetch(`/api/regions?${params}`, { signal })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as PlaceResult[]
}

// Bounding box of a Polygon or MultiPolygon.
export function geometryBox(g: RegionGeometry): BBox {
  const pts = g.type === 'Polygon' ? g.coordinates.flat() : g.coordinates.flat(2)
  const xs = pts.map((c) => c[0])
  const ys = pts.map((c) => c[1])
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]
}

// One box covering all the given boxes: the viewbox sent to Nominatim.
export function unionBox(boxes: BBox[]): BBox | null {
  if (boxes.length === 0) return null
  return [
    Math.min(...boxes.map((b) => b[0])),
    Math.min(...boxes.map((b) => b[1])),
    Math.max(...boxes.map((b) => b[2])),
    Math.max(...boxes.map((b) => b[3])),
  ]
}

// Even-odd ray casting over every ring, so holes are excluded.
function inRings(x: number, y: number, rings: number[][][]): boolean {
  let inside = false
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i]
      const [xj, yj] = ring[j]
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
    }
  }
  return inside
}

function inShape(x: number, y: number, g: RegionGeometry): boolean {
  return g.type === 'Polygon' ? inRings(x, y, g.coordinates) : g.coordinates.some((poly) => inRings(x, y, poly))
}

// The viewbox covers all areas at once, so a second pass keeps only places that meet one of them:
// points (no outline) must fall inside an area's shape; outlined places must overlap an area's box.
export function placeInAreas(place: PlaceResult, areas: RegionGeometry[]): boolean {
  const [w, s, e, n] = place.bbox
  if (!place.geometry) {
    const x = (w + e) / 2
    const y = (s + n) / 2
    return areas.some((a) => inShape(x, y, a))
  }
  return areas.some((a) => {
    const b = geometryBox(a)
    return w <= b[2] && b[0] <= e && s <= b[3] && b[1] <= n
  })
}
