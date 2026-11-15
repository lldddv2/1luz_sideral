import type { AoiPolygon, LngLat, RegionGeometry } from './types'

const EARTH_RADIUS_M = 6378137

// Geodesic area of an open ring in km² (spherical approximation, same formula as turf.js).
export function ringAreaKm2(coords: LngLat[]): number {
  const rad = (d: number) => (d * Math.PI) / 180
  let total = 0
  for (let i = 0; i < coords.length; i++) {
    const [lon1, lat1] = coords[i]
    const [lon2, lat2] = coords[(i + 1) % coords.length]
    total += rad(lon2 - lon1) * (2 + Math.sin(rad(lat1)) + Math.sin(rad(lat2)))
  }
  return Math.abs((total * EARTH_RADIUS_M * EARTH_RADIUS_M) / 2) / 1e6
}

// GeoJSON geometry of any shape (drawn shapes are single-ring polygons).
export function shapeGeometry(shape: AoiPolygon): RegionGeometry {
  if (shape.geometry) return shape.geometry
  return { type: 'Polygon', coordinates: [[...shape.coords, shape.coords[0]]] }
}

const polygonsOf = (g: RegionGeometry) => (g.type === 'Polygon' ? [g.coordinates] : g.coordinates)

// Area in km²: outer rings minus holes.
export function geometryAreaKm2(g: RegionGeometry): number {
  return polygonsOf(g).reduce(
    (sum, rings) =>
      sum + rings.reduce((acc, ring, i) => acc + (i === 0 ? 1 : -1) * ringAreaKm2(ring as LngLat[]), 0),
    0,
  )
}

// [west, south, east, north]
export function geometryBbox(g: RegionGeometry): [number, number, number, number] {
  let [w, s, e, n] = [Infinity, Infinity, -Infinity, -Infinity]
  for (const rings of polygonsOf(g))
    for (const [x, y] of rings[0]) {
      w = Math.min(w, x)
      s = Math.min(s, y)
      e = Math.max(e, x)
      n = Math.max(n, y)
    }
  return [w, s, e, n]
}

export type Ring = number[][]

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
export const inPolygon = (rings: Ring[], p: LngLat): boolean =>
  inRing(rings[0], p) && !rings.slice(1).some((hole) => inRing(hole, p))

// True when the point lies inside any shape (drawn polygon or administrative region).
export const inAnyShape = (shapes: AoiPolygon[], p: LngLat): boolean =>
  shapes.some((s) => {
    const g = shapeGeometry(s)
    return g.type === 'Polygon' ? inPolygon(g.coordinates, p) : g.coordinates.some((poly) => inPolygon(poly, p))
  })
