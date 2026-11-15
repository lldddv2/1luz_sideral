import type { FeatureCollection } from 'geojson'
import type { DateRange } from './passes'
import type { LngLat, NisarOverlay, NisarPol, NisarScene, RegionGeometry } from './types'

// Demo study area over Lake Pontchartrain, where the AWS pipeline cropped NISAR GCOV scenes.
export const NISAR_DEMO = {
  name: 'Lake Pontchartrain (NISAR demo)',
  coords: [
    [-90.15306303, 29.95606402],
    [-90.0495598, 29.95378523],
    [-90.0468903, 30.04391117],
    [-90.15048687, 30.04619821],
  ] as LngLat[],
  start: '2026-10-21',
  end: '2026-11-15',
}

const OVERLAY_WIDTH = 512

interface QueryFeature {
  geometry: RegionGeometry
  properties: {
    scene_id: string
    acquired_at: string
    track?: number | null
    frame?: number | null
    direction?: string | null
    regions: { id: string; coverage_pct: number }[]
  }
}

// Scenes meeting the area in the range, oldest first. Throws on any non-2xx status (501 without a bucket).
export async function fetchNisarScenes(
  geometry: RegionGeometry,
  range: DateRange,
  signal: AbortSignal,
): Promise<NisarScene[]> {
  const res = await fetch('/api/scenes/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      regions: { type: 'FeatureCollection', features: [{ type: 'Feature', properties: { id: 'aoi' }, geometry }] },
      start: `${range.start}T00:00:00Z`,
      end: `${range.end}T23:59:59Z`,
      source: 'nisar',
    }),
    signal,
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const fc = (await res.json()) as { features: QueryFeature[] }
  return fc.features.map(({ geometry, properties: p }) => ({
    scene_id: p.scene_id,
    acquired_at: p.acquired_at,
    track: p.track ?? null,
    frame: p.frame ?? null,
    direction: p.direction ?? null,
    coverage_pct: p.regions[0]?.coverage_pct ?? 0,
    footprint: geometry,
  }))
}

// Default pick: the best-covering scene, the most recent among ties.
export function defaultScene(scenes: NisarScene[]): NisarScene | null {
  return (
    [...scenes].sort((a, b) => b.coverage_pct - a.coverage_pct || b.acquired_at.localeCompare(a.acquired_at))[0] ??
    null
  )
}

export async function fetchNisarOverlay(
  sceneId: string,
  geometry: RegionGeometry,
  pol: NisarPol,
  signal: AbortSignal,
): Promise<NisarOverlay> {
  const res = await fetch(`/api/scenes/${encodeURIComponent(sceneId)}/data`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ geometry, format: 'png', width: OVERLAY_WIDTH, source: 'nisar', polarization: pol }),
    signal,
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const corners = JSON.parse(res.headers.get('X-Corners-WGS84') ?? 'null')
  if (!Array.isArray(corners) || corners.length !== 4) throw new Error('missing X-Corners-WGS84')
  const url = URL.createObjectURL(await res.blob())
  return { sceneId, pol, url, corners: corners as NisarOverlay['corners'] }
}

export const footprintsOf = (scenes: NisarScene[], selected: string | null): FeatureCollection => ({
  type: 'FeatureCollection',
  features: scenes.map((s) => ({
    type: 'Feature',
    properties: { selected: s.scene_id === selected },
    geometry: s.footprint,
  })),
})

export const sceneLabel = (s: NisarScene) =>
  `${s.acquired_at.slice(0, 10)} · ${s.track ?? '?'}/${s.frame ?? '?'} · ${s.coverage_pct.toFixed(1)}%`
