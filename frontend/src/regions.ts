// Administrative boundaries fetched on demand:
// - countries: Natural Earth 1:50m (jsDelivr CDN)
// - subdivisions: geoBoundaries gbOpen (ADM1 = departments/states, ADM2 = municipalities)
import type { FeatureCollection } from 'geojson'
import type { LngLat, RegionGeometry } from './types'

export type AdminLevel = 'ADM0' | 'ADM1' | 'ADM2'

export interface RegionProps {
  rid: string // unique id: "c:<ISO3>" for countries, "s:<level>:<shapeID>" for subdivisions
  name: string
  iso: string
}

export type RegionCollection = FeatureCollection<RegionGeometry, RegionProps>

const COUNTRIES_URL =
  'https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/geojson/ne_50m_admin_0_countries.geojson'
const GEOBOUNDARIES_API = 'https://www.geoboundaries.org/api/current/gbOpen'

const getJson = async (url: string) => {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`)
  return res.json()
}

let countries: Promise<RegionCollection> | null = null

export function loadCountries(): Promise<RegionCollection> {
  if (!countries) {
    countries = getJson(COUNTRIES_URL).then((fc) => ({
      type: 'FeatureCollection',
      features: fc.features.map((f: { geometry: RegionGeometry; properties: Record<string, string> }) => {
        const p = f.properties
        // Natural Earth uses "-99" when ISO_A3 is not assigned (e.g. France, Norway).
        const iso = [p.ISO_A3, p.ISO_A3_EH, p.ADM0_A3].find((c) => c && c !== '-99') ?? ''
        return {
          type: 'Feature',
          geometry: f.geometry,
          properties: { rid: `c:${iso}`, name: p.NAME_ES || p.NAME, iso },
        }
      }),
    }))
    countries.catch(() => (countries = null))
  }
  return countries
}

// geoBoundaries files live in Git LFS. github.com/<o>/<r>/raw/... redirects without CORS headers,
// so point straight at the LFS media host, which allows cross-origin requests.
const toMediaUrl = (url: string) =>
  url.replace(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/raw\//, 'https://media.githubusercontent.com/media/$1/$2/')

const subdivisions = new Map<string, Promise<RegionCollection>>()

export function loadSubdivisions(iso: string, level: Exclude<AdminLevel, 'ADM0'>): Promise<RegionCollection> {
  const key = `${iso}/${level}`
  let promise = subdivisions.get(key)
  if (!promise) {
    promise = getJson(`${GEOBOUNDARIES_API}/${iso}/${level}/`)
      .then((meta) => getJson(toMediaUrl(meta.simplifiedGeometryGeoJSON)))
      .then((fc) => ({
        type: 'FeatureCollection',
        features: fc.features.map(
          (f: { geometry: RegionGeometry; properties: Record<string, string> }, i: number) => ({
            type: 'Feature',
            geometry: f.geometry,
            properties: { rid: `s:${level}:${f.properties.shapeID ?? i}`, name: f.properties.shapeName, iso },
          }),
        ),
      }))
    promise.catch(() => subdivisions.delete(key))
    subdivisions.set(key, promise)
  }
  return promise
}

type Ring = number[][]

// Ray casting: a point is inside when a ray to its right crosses the ring an odd number of times.
const inRing = (ring: Ring, [x, y]: LngLat): boolean => {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

// rings[0] is the outer ring; the rest are holes.
const inPolygon = (rings: Ring[], p: LngLat): boolean =>
  inRing(rings[0], p) && !rings.slice(1).some((hole) => inRing(hole, p))

// First feature whose outline contains p = [lng, lat], or undefined.
export function findCountryAt(fc: RegionCollection, p: LngLat) {
  return fc.features.find((f) =>
    f.geometry.type === 'Polygon'
      ? inPolygon(f.geometry.coordinates, p)
      : f.geometry.coordinates.some((poly) => inPolygon(poly, p)),
  )
}
