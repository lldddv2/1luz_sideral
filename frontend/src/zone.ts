import type { LngLat, UserZone } from './types'
import type { Polygon } from 'geojson'

// Mean km per degree of latitude; longitude degrees shrink by cos(lat).
const KM_PER_DEG = 111.32

export const ZONE_DEFAULT_HALF_KM = 5
export const ZONE_MIN_SIDE_KM = 1
export const ZONE_MAX_SIDE_KM = 100

export const clampHalfKm = (half: number) =>
  Math.min(ZONE_MAX_SIDE_KM / 2, Math.max(ZONE_MIN_SIDE_KM / 2, half))

const kmPerDegLon = (lat: number) => KM_PER_DEG * Math.max(Math.cos((lat * Math.PI) / 180), 0.01)

// Square around the center as [west, south, east, north].
export function zoneBbox({ center: [lon, lat], halfSizeKm }: UserZone): [number, number, number, number] {
  const dLat = halfSizeKm / KM_PER_DEG
  const dLon = halfSizeKm / kmPerDegLon(lat)
  return [lon - dLon, lat - dLat, lon + dLon, lat + dLat]
}

// Corners in ring order: SW, SE, NE, NW.
export function zoneCorners(zone: UserZone): LngLat[] {
  const [w, s, e, n] = zoneBbox(zone)
  return [[w, s], [e, s], [e, n], [w, n]]
}

// Half size from a dragged corner: the larger axis distance to the center wins.
export function halfKmFromCorner(center: LngLat, corner: LngLat): number {
  const dy = Math.abs(corner[1] - center[1]) * KM_PER_DEG
  const dx = Math.abs(corner[0] - center[0]) * kmPerDegLon(center[1])
  return clampHalfKm(Math.max(dx, dy))
}

// Closed GeoJSON ring of the square, the geometry the download sends to the backend.
export function zoneGeometry(zone: UserZone): Polygon {
  const ring = zoneCorners(zone)
  return { type: 'Polygon', coordinates: [[...ring, ring[0]]] }
}

// Name shown for a point: its own, or its 1-based position in the list.
export const zoneLabel = (zone: UserZone, index: number) => zone.name?.trim() || `Point ${index + 1}`
