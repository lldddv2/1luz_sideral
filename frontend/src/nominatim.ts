import type { RegionGeometry } from './types'

// Place search over OpenStreetMap Nominatim.
// Usage policy: at most one request per second, no autocomplete. The browser sends Referer itself;
// no custom headers are added (they would force a CORS preflight).

// [west, south, east, north], the order used by fitBounds.
export type BBox = [number, number, number, number]

export interface PlaceResult {
  id: string
  name: string
  label: string // full display name, e.g. "Antioquia, Colombia"
  type: string // OSM address type, e.g. "state" or "city"
  bbox: BBox
  geometry: RegionGeometry | null // administrative boundary; null for points and lines
}

// Fields used from a Nominatim jsonv2 item.
interface NominatimItem {
  place_id: number
  name?: string
  display_name: string
  type?: string
  addresstype?: string
  boundingbox: [string, string, string, string] // [south, north, west, east]
  geojson?: { type: string; coordinates: unknown }
}

export async function searchPlaces(q: string, signal?: AbortSignal): Promise<PlaceResult[]> {
  const url =
    `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}` +
    '&format=jsonv2&polygon_geojson=1&limit=8&accept-language=es'
  const res = await fetch(url, { signal })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const items = (await res.json()) as NominatimItem[]
  return items.map((it): PlaceResult => {
    const [s, n, w, e] = it.boundingbox.map(Number)
    const g = it.geojson
    const isArea = g?.type === 'Polygon' || g?.type === 'MultiPolygon'
    return {
      id: String(it.place_id),
      name: it.name || it.display_name.split(',')[0],
      label: it.display_name,
      type: it.addresstype ?? it.type ?? '',
      bbox: [w, s, e, n],
      geometry: isArea ? (g as RegionGeometry) : null,
    }
  })
}
