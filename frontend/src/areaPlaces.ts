import { useEffect, useState } from 'react'
import { pointInShapes } from './features'
import { geometryBbox } from './geo'
import type { RegionGeometry } from './types'

// Place names drawn by the app itself while study areas exist. The Esri reference labels are
// raster tiles: they cannot be filtered name by name nor clipped to a polygon, so they are hidden
// and these OpenStreetMap places (inside the true area shapes) take their place.

export type PlaceRank = 'state' | 'city' | 'town' | 'village'

export interface AreaPlace {
  id: number
  name: string
  rank: PlaceRank
  lon: number
  lat: number
}

// Zoom from which each rank is shown.
export const PLACE_MINZOOM: Record<PlaceRank, number> = { state: 5, city: 6, town: 8, village: 12 }

const OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
const MAX_PLACES = 200
// Over this bbox area (km²) villages are skipped: a large region would return thousands.
const VILLAGE_MAX_KM2 = 20000
const DEBOUNCE_MS = 600
const RANK_ORDER: PlaceRank[] = ['state', 'city', 'town', 'village']

type BBox = [number, number, number, number]

function boxKm2([w, s, e, n]: BBox): number {
  const midLat = ((s + n) / 2) * (Math.PI / 180)
  return (e - w) * 111.32 * Math.cos(midLat) * (n - s) * 110.57
}

interface OverpassNode {
  id: number
  lat: number
  lon: number
  tags?: Record<string, string>
}

const cache = new Map<string, AreaPlace[]>()

async function fetchAreaPlaces(shapes: RegionGeometry[], signal: AbortSignal): Promise<AreaPlace[]> {
  const boxes = shapes.map(geometryBbox)
  const withVillages = boxes.reduce((sum, b) => sum + boxKm2(b), 0) <= VILLAGE_MAX_KM2
  const ranks = withVillages ? 'state|city|town|village' : 'state|city|town'
  // Overpass bbox order is south,west,north,east.
  const parts = boxes.map(([w, s, e, n]) => `node["place"~"^(${ranks})$"]["name"](${s},${w},${n},${e});`).join('')
  const query = `[out:json][timeout:25];(${parts});out tags 2000;`
  const res = await fetch(OVERPASS_URL, {
    method: 'POST',
    body: new URLSearchParams({ data: query }),
    signal,
  })
  if (!res.ok) throw new Error(`Overpass HTTP ${res.status}`)
  const body = (await res.json()) as { elements: OverpassNode[] }
  const places = body.elements
    .filter((el) => el.tags?.name && pointInShapes(el.lon, el.lat, shapes))
    .map((el) => ({
      id: el.id,
      name: el.tags!['name:es'] ?? el.tags!.name,
      rank: el.tags!.place as PlaceRank,
      lon: el.lon,
      lat: el.lat,
      pop: Number(el.tags!.population) || 0,
    }))
  // Keep the most important ones: higher rank first, then larger population.
  places.sort((a, b) => RANK_ORDER.indexOf(a.rank) - RANK_ORDER.indexOf(b.rank) || b.pop - a.pop)
  const seen = new Set<number>()
  return places
    .filter((p) => (seen.has(p.id) ? false : (seen.add(p.id), true)))
    .slice(0, MAX_PLACES)
    .map(({ pop: _pop, ...p }) => p)
}

// Null when there is no study area: the map then keeps the raster reference labels.
export function useAreaPlaces(shapes: RegionGeometry[]): AreaPlace[] | null {
  const key = shapes.length ? JSON.stringify(shapes) : ''
  const [places, setPlaces] = useState<AreaPlace[]>([])

  useEffect(() => {
    if (!key) return
    const cached = cache.get(key)
    if (cached) {
      setPlaces(cached)
      return
    }
    setPlaces([])
    const ac = new AbortController()
    const timer = setTimeout(() => {
      fetchAreaPlaces(shapes, ac.signal)
        .then((found) => {
          cache.set(key, found)
          setPlaces(found)
        })
        .catch(() => {
          // Network or Overpass error: leave the area without names rather than block the map.
          if (!ac.signal.aborted) setPlaces([])
        })
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      ac.abort()
    }
    // shapes is captured through key: same key, same geometry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return key ? places : null
}
