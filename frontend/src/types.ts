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
