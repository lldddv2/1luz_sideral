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

// Raw GeoJSON persisted in the Cache API. Bump the name if the URL format changes.
const CACHE_NAME = 'boundaries-v1'

// Cache API is optional: missing (insecure context) or failing (private mode, quota) just means network.
const cacheJson = async (url: string) => {
  if (typeof caches === 'undefined') return null
  try {
    const cache = await caches.open(CACHE_NAME)
    const hit = await cache.match(url)
    return hit ? await hit.json() : null
  } catch {
    return null
  }
}

const storeJson = async (url: string, res: Response) => {
  if (typeof caches === 'undefined') return
  try {
    const cache = await caches.open(CACHE_NAME)
    await cache.put(url, res)
  } catch {
    // Ignore: the network response is already usable.
  }
}

const getJson = async (url: string, useCache = false) => {
  if (useCache) {
    const cached = await cacheJson(url)
    if (cached) return cached
  }
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`)
  if (useCache) void storeJson(url, res.clone())
  return res.json()
}

let countries: Promise<RegionCollection> | null = null

export function loadCountries(): Promise<RegionCollection> {
  if (!countries) {
    countries = getJson(COUNTRIES_URL, true).then((fc) => ({
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

// geoBoundaries release paths are deterministic, so the metadata API call (~3.5 s) is skipped.
const DIRECT_COMMIT = '9469f09'
const directUrl = (iso: string, level: Exclude<AdminLevel, 'ADM0'>) =>
  toMediaUrl(
    `https://github.com/wmgeolab/geoBoundaries/raw/${DIRECT_COMMIT}/releaseData/gbOpen/${iso}/${level}/geoBoundaries-${iso}-${level}_simplified.geojson`,
  )

// Direct URL first; fall back to the metadata API once if the pinned file moved.
const fetchSubdivisions = async (iso: string, level: Exclude<AdminLevel, 'ADM0'>) => {
  try {
    return await getJson(directUrl(iso, level), true)
  } catch {
    const meta = await getJson(`${GEOBOUNDARIES_API}/${iso}/${level}/`)
    return getJson(toMediaUrl(meta.simplifiedGeometryGeoJSON), true)
  }
}

const subdivisions = new Map<string, Promise<RegionCollection>>()

export function loadSubdivisions(iso: string, level: Exclude<AdminLevel, 'ADM0'>): Promise<RegionCollection> {
  const key = `${iso}/${level}`
  let promise = subdivisions.get(key)
  if (!promise) {
    promise = fetchSubdivisions(iso, level)
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
