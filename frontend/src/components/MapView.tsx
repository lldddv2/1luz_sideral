import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import Map, { AttributionControl, Layer, Marker, Source } from 'react-map-gl/maplibre'
import type { MapLayerMouseEvent, MapRef } from 'react-map-gl/maplibre'
import type { Map as MaplibreMap, StyleSpecification } from 'maplibre-gl'
import type { FeatureCollection } from 'geojson'
import type { AoiPolygon, DrawMode, LngLat, RegionGeometry, UserZone } from '../types'
import { halfKmFromCorner, zoneBbox, zoneCorners } from '../zone'
import type { BBox } from '../nominatim'
import { inAnyShape, shapeGeometry } from '../geo'
import { POI_COLOR, POIS } from '../pois'
import PoiPanel from './PoiPanel'
import type { CoverMaskImage } from '../landcover'
import { CATEGORY_COLOR } from '../features'
import type { NaturalFeature } from '../features'
import { PLACE_MINZOOM } from '../areaPlaces'
import type { AreaPlace } from '../areaPlaces'
import type { RegionCollection } from '../regions'
import type { MapViewport } from '../useRegionPicker'
import { angleFrom, centroid, resizeCorner, resizeEdge, rotate, rotateHandle } from '../editing'
import type { XY } from '../editing'
import { TOOLS } from './Sidebar'
import { addProtocol } from 'maplibre-gl'
import { NISAR_ASC_COLOR, NISAR_DESC_COLOR, NISAR_FADE_END, NISAR_FADE_START, NISAR_OUTLINE_MAXZOOM, NISAR_PROTOCOL, DSWX_PROTOCOL, OVERLAYS, OVERLAY_IDS, cancelPreload, nisarDate, nisarFootprints as fetchNisarFootprints, overlayTiles, preloadAround, registerNisarProtocol, takeFailedTiles } from '../layers'
import type { OverlayId, OverlayState, PreloadLayer } from '../layers'

// Overlay tile failures (e.g. GIBS hiccups) are expected; keep them out of the console.
registerNisarProtocol(addProtocol)

const OVERLAY_SOURCES = new Set(OVERLAY_IDS.map((id) => `ov-${id}`))
const EMPTY_FC: FeatureCollection = { type: 'FeatureCollection', features: [] }

// Pixel tolerances for drawing interactions.
const DUPLICATE_PX = 5 // clicks this close to the last vertex are ignored (double-click)
const CLOSE_PX = 10 // clicking this close to the first vertex closes the polygon
// Point of interest: the square shows once its on-screen side passes SHOW, and collapses
// into a pin below HIDE. The gap between both keeps it from flickering at the threshold.
const ZONE_SQUARE_SHOW_PX = 44
const ZONE_SQUARE_HIDE_PX = 36

// Approximate palette size, used to clamp it inside the map container.
const PALETTE_W = 112
const PALETTE_H = 44
const PALETTE_MARGIN = 8

// Axis-aligned rectangle from two opposite corners, as an open ring.
const rectangleFrom = ([x1, y1]: LngLat, [x2, y2]: LngLat): LngLat[] => [
  [x1, y1],
  [x2, y1],
  [x2, y2],
  [x1, y2],
]

// Circular-arrow cursor for the rotation handle (CSS has no built-in rotate cursor).
const ROTATE_CURSOR =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke-linecap='round'><g stroke='white' stroke-width='4'><path d='M20 12a8 8 0 1 1-2.3-5.7'/><path d='M20 4v5h-5'/></g><g stroke='black' stroke-width='2'><path d='M20 12a8 8 0 1 1-2.3-5.7'/><path d='M20 4v5h-5'/></g></svg>\") 12 12, crosshair"

// Picks the CSS resize arrow closest to a screen-space direction (y grows downward).
const resizeCursor = (dx: number, dy: number): string => {
  const deg = ((Math.atan2(dy, dx) * 180) / Math.PI + 180) % 180
  if (deg < 22.5 || deg >= 157.5) return 'ew-resize'
  if (deg < 67.5) return 'nwse-resize'
  if (deg < 112.5) return 'ns-resize'
  return 'nesw-resize'
}

interface Props {
  basemap: StyleSpecification
  labels: { tiles: string; maxzoom: number; withOverlaysOnly?: boolean }
  // Place names inside the study areas; null when there are none (raster reference labels show instead).
  areaPlaces: AreaPlace[] | null
  polygons: AoiPolygon[]
  mode: DrawMode | null
  onSelectMode: (mode: DrawMode) => void
  regionCountries: RegionCollection | null
  regionSubdivisions: RegionCollection | null
  onRegionClick: (rid: string) => void
  onHoverRegion: (rid: string | null) => void
  onViewChange: (view: MapViewport) => void
  onShapeComplete: (kind: DrawMode, coords: LngLat[]) => void
  onCancelDrawing: () => void
  onDelete: (id: string) => void
  onHover: (id: string | null) => void
  onUpdate: (id: string, coords: LngLat[]) => void
  previewGeometry: RegionGeometry | null // search result outline, drawn dashed; not an AOI
  flyToBbox: { bbox: BBox; key: number } | null // camera target; a new key flies there again
  searchStart: string // search date range (YYYY-MM-DD), drives the POI popup timeline
  searchEnd: string
  overlays: Record<OverlayId, OverlayState>
  coverMask: CoverMaskImage | null // land-cover classes of the filter, over the active area
  featureLabels: NaturalFeature[] // natural features labelled on the map (one marker each)
  activeFeature: NaturalFeature | null // last feature picked; its label offers "add as study area"
  onFeatureClick: (feature: NaturalFeature) => void
  onFeatureAdd: (feature: NaturalFeature) => void
  zones: UserZone[] // user points of interest, each with its square range (annotation only)
  selectedZoneId: string | null
  onSelectZone: (id: string) => void
  zonePlacing: boolean // next map click adds a zone center
  onZonePlace: (center: LngLat) => void
  onZoneChange: (zone: UserZone) => void
  onCancelZone: () => void
}

// Active drag while editing the selected shape.
type Drag =
  | { kind: 'vertex'; index: number; origin: LngLat[] }
  | { kind: 'edge'; index: number; start: LngLat; origin: LngLat[] }
  | { kind: 'rotate'; center: XY; startAngle: number; anchorIndex: number; origin: LngLat[] }
  | { kind: 'shape'; start: LngLat; origin: LngLat[] }

// vertex: polygon vertex / rectangle corner; mid: polygon edge midpoint (adds a vertex);
// edge: rectangle side (one-side resize); rotate: rotation handle.
interface HandleProps {
  kind: 'vertex' | 'mid' | 'edge' | 'rotate'
  index: number
  key: string
}

// Shape fills: editable shapes and administrative regions live in separate sources.
const isAoiFill = (layerId: string) => layerId === 'aoi-fill' || layerId === 'aoi-region-fill'

interface ContextMenu {
  x: number
  y: number
  id: string
  name: string
}

export default function MapView({
  basemap,
  labels,
  areaPlaces,
  polygons,
  mode,
  onSelectMode,
  regionCountries,
  regionSubdivisions,
  onRegionClick,
  onHoverRegion,
  onViewChange,
  onShapeComplete,
  onCancelDrawing,
  onDelete,
  onHover,
  onUpdate,
  previewGeometry,
  flyToBbox,
  searchStart,
  searchEnd,
  overlays,
  coverMask,
  featureLabels,
  activeFeature,
  onFeatureClick,
  onFeatureAdd,
  zones,
  selectedZoneId,
  onSelectZone,
  zonePlacing,
  onZonePlace,
  onZoneChange,
  onCancelZone,
}: Props) {
  // Placing the zone center blocks the same interactions as shape drawing.
  const drawing = mode !== null || zonePlacing
  const mapRef = useRef<MapRef>(null)
  const [vertices, setVertices] = useState<LngLat[]>([])
  const [cursor, setCursor] = useState<LngLat | null>(null)
  const [menu, setMenu] = useState<ContextMenu | null>(null)
  const [palette, setPalette] = useState<{ x: number; y: number } | null>(null)
  const paletteRef = useRef<HTMLDivElement>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [drag, setDrag] = useState<Drag | null>(null)
  const [hoverHandle, setHoverHandle] = useState<string | null>(null)
  const [mapCursor, setMapCursor] = useState('')
  // Whole zoom level only, so area place labels re-render on level changes, not every frame.
  const [zoomLevel, setZoomLevel] = useState(4)
  const [hoverRegion, setHoverRegion] = useState<string | null>(null)
  const selected = polygons.find((p) => p.id === selectedId)
  const [poiId, setPoiId] = useState<string | null>(null)
  // Only POIs inside some study area are shown; no areas, no points.
  const poisGeo = useMemo<FeatureCollection>(
    () => ({
      type: 'FeatureCollection',
      features: POIS.features.filter((f) => inAnyShape(polygons, f.geometry.coordinates as LngLat)),
    }),
    [polygons],
  )
  // NISAR frame footprints for the current view (CMR), drawn as outlines colored by orbit direction.
  const nisar = overlays.nisar
  const nisarDirs = ((nisar.asc ?? true) ? 'A' : '') + ((nisar.desc ?? true) ? 'D' : '') || 'N'
  const showFoot = nisar.on && (nisar.outline ?? true)
  const footDate = nisarDate(nisar.date)
  const [footView, setFootView] = useState<[number, number, number, number] | null>(null)
  const [nisarFoot, setNisarFoot] = useState<FeatureCollection>(EMPTY_FC)
  useEffect(() => {
    if (!showFoot || !footView) return
    let live = true
    fetchNisarFootprints(footView, footDate)
      .then((fps) => {
        if (!live) return
        setNisarFoot({
          type: 'FeatureCollection',
          features: fps.map((f) => ({
            type: 'Feature',
            properties: { dir: f.dir },
            geometry: { type: 'MultiLineString', coordinates: f.rings },
          })),
        })
      })
      .catch(() => live && setNisarFoot(EMPTY_FC)) // view too large or CMR down
    return () => {
      live = false
    }
  }, [showFoot, footView, footDate])
  // Tile preload: 300 ms after the map settles, fetch raw tiles around the view, then z-1 and z+1.
  const dswx = overlays.dswx
  useEffect(() => {
    const map = mapRef.current?.getMap()
    if (!footView || !map) return
    const layers: PreloadLayer[] = []
    if (nisar.on) layers.push({ id: 'nisar', date: nisar.date, dirs: nisarDirs })
    if (dswx.on) layers.push({ id: 'dswx', date: dswx.date })
    if (!layers.length) return
    const t = setTimeout(() => void preloadAround(map.getZoom(), footView, layers), 300)
    return () => {
      clearTimeout(t)
      cancelPreload()
    }
  }, [footView, nisar.on, nisar.date, nisarDirs, dswx.on, dswx.date])
  // Look the POI up by id: rendered feature properties flatten nested objects.
  const openPoi = poiId ? poisGeo.features.find((f) => f.properties?.id === poiId) : undefined
  const poi = openPoi ? POIS.features.find((f) => f.properties.id === poiId) : undefined

  // Escape closes the POI popup.
  useEffect(() => {
    if (!poiId) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setPoiId(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [poiId])

  // Escape deselects the shape being edited.
  useEffect(() => {
    if (!selectedId) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setSelectedId(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedId])

  // End a drag even if the mouse is released outside the map.
  useEffect(() => {
    if (!drag) return
    const onUp = () => {
      setDrag(null)
      mapRef.current?.getMap().dragPan.enable()
    }
    window.addEventListener('mouseup', onUp)
    return () => window.removeEventListener('mouseup', onUp)
  }, [drag])

  // Cursor per handle; resize arrows follow the on-screen direction of the corner or side.
  const handleCursor = (h: HandleProps): string => {
    if (h.kind === 'mid') return 'copy'
    if (h.kind === 'rotate') return ROTATE_CURSOR
    const map = mapRef.current
    if (!selected || selected.kind !== 'rectangle' || !map) return 'move'
    const c = map.project(selected.coords[h.index])
    if (h.kind === 'edge') {
      // A side moves along its normal.
      const n = map.project(selected.coords[(h.index + 1) % 4])
      return resizeCursor(-(n.y - c.y), n.x - c.x)
    }
    const o = map.project(selected.coords[(h.index + 2) % 4])
    return resizeCursor(c.x - o.x, c.y - o.y)
  }

  // Keeps the tool palette inside the map container.
  const clampPalette = (x: number, y: number) => {
    const el = mapRef.current?.getMap().getContainer()
    if (!el) return { x, y }
    return {
      x: Math.max(PALETTE_MARGIN, Math.min(x, el.clientWidth - PALETTE_W - PALETTE_MARGIN)),
      y: Math.max(PALETTE_MARGIN, Math.min(y, el.clientHeight - PALETTE_H - PALETTE_MARGIN)),
    }
  }

  const handleMouseDown = (e: MapLayerMouseEvent) => {
    if (e.originalEvent.button === 1) {
      // Middle click opens the tool palette; preventDefault blocks Chrome's autoscroll.
      e.originalEvent.preventDefault()
      setMenu(null)
      setPalette(clampPalette(e.point.x, e.point.y))
      return
    }
    if (drawing || !selected || e.originalEvent.button !== 0) return
    const top = e.features?.[0]
    const p: LngLat = [e.lngLat.lng, e.lngLat.lat]
    const origin = selected.coords
    if (top?.layer.id === 'edit-handles') {
      const h = top.properties as HandleProps
      if (h.kind === 'mid') {
        // Dragging a midpoint inserts a new vertex there and drags it.
        const coords = [...origin.slice(0, h.index + 1), p, ...origin.slice(h.index + 1)]
        onUpdate(selected.id, coords)
        setDrag({ kind: 'vertex', index: h.index + 1, origin: coords })
      } else if (h.kind === 'edge') {
        setDrag({ kind: 'edge', index: h.index, start: p, origin })
      } else if (h.kind === 'rotate') {
        if (selected.kind === 'region') return
        const center = centroid(origin)
        const anchorIndex = rotateHandle(origin, selected.kind)[2]
        setDrag({ kind: 'rotate', center, startAngle: angleFrom(center, p), anchorIndex, origin })
      } else {
        setDrag({ kind: 'vertex', index: h.index, origin })
      }
    } else if (top?.layer.id === 'aoi-fill' && top.properties.id === selected.id) {
      setDrag({ kind: 'shape', start: p, origin })
    } else {
      return
    }
    e.preventDefault()
    mapRef.current?.getMap().dragPan.disable()
  }

  // Close the context menu and the tool palette with Escape.
  useEffect(() => {
    if (!menu && !palette) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setMenu(null)
      setPalette(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menu, palette])

  // Chrome shows its autoscroll widget on middle click; block the follow-up auxclick too.
  // The map instance is not ready during mount effects, so the container is resolved per event.
  useEffect(() => {
    const onAux = (e: MouseEvent) => {
      if (e.button !== 1) return
      const container = mapRef.current?.getMap().getContainer()
      if (!container || !(e.target instanceof Node) || !container.contains(e.target)) return
      e.preventDefault()
    }
    window.addEventListener('auxclick', onAux)
    return () => window.removeEventListener('auxclick', onAux)
  }, [])

  // Shift+T opens the palette at the map center; ignored while typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.key.toLowerCase() !== 't') return
      const target = e.target as HTMLElement | null
      if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return
      const el = mapRef.current?.getMap().getContainer()
      if (!el) return
      e.preventDefault()
      setMenu(null)
      setPalette(clampPalette(el.clientWidth / 2 - PALETTE_W / 2, el.clientHeight / 2 - PALETTE_H / 2))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Focus the first tool so Tab and Enter work as soon as the palette opens.
  // On close, give focus back to where it was if it would otherwise fall to <body>.
  const paletteOpen = palette !== null
  useEffect(() => {
    if (!paletteOpen) return
    const previous = document.activeElement as HTMLElement | null
    paletteRef.current?.querySelector('button')?.focus()
    return () => {
      if (document.activeElement === document.body || !document.activeElement) previous?.focus()
    }
  }, [paletteOpen])

  const handleContextMenu = (e: MapLayerMouseEvent) => {
    e.originalEvent.preventDefault()
    setPalette(null)
    const feature = e.features?.find((f) => isAoiFill(f.layer.id))
    if (drawing || !feature) {
      setMenu(null)
      return
    }
    setMenu({ x: e.point.x, y: e.point.y, id: feature.properties.id, name: feature.properties.name })
  }

  // Reset the in-progress sketch (and any selection) whenever drawing mode changes.
  useEffect(() => {
    setVertices([])
    setCursor(null)
    setSelectedId(null)
    setHoverRegion(null)
    onHoverRegion(null)
  }, [mode]) // eslint-disable-line react-hooks/exhaustive-deps

  // Region hover uses feature-state: only the hovered feature is repainted, not the whole layer.
  useEffect(() => {
    const map = mapRef.current?.getMap()
    if (!map || !hoverRegion) return
    const target = { source: hoverRegion.startsWith('s:') ? 'region-sub' : 'region-countries', id: hoverRegion }
    if (map.getSource(target.source)) map.setFeatureState(target, { hover: true })
    return () => {
      if (map.getSource(target.source)) map.setFeatureState(target, { hover: false })
    }
  }, [hoverRegion])

  // Fly to a search result. Keyed by `key`, so the same result can be flown to again.
  const flyKey = flyToBbox?.key
  useEffect(() => {
    if (!flyToBbox) return
    const [w, s, e, n] = flyToBbox.bbox
    mapRef.current?.getMap().fitBounds(
      [
        [w, s],
        [e, n],
      ],
      { padding: 60, duration: 1200 },
    )
  }, [flyKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // Placing the zone center: Escape cancels.
  useEffect(() => {
    if (!zonePlacing) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancelZone()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [zonePlacing]) // eslint-disable-line react-hooks/exhaustive-deps

  const pixelDistance = (a: LngLat, b: LngLat) => {
    const map = mapRef.current
    if (!map) return Infinity
    const pa = map.project(a)
    const pb = map.project(b)
    return Math.hypot(pa.x - pb.x, pa.y - pb.y)
  }

  const finish = (coords: LngLat[]) => {
    if (mode === 'polygon' && coords.length >= 3) onShapeComplete('polygon', coords)
  }

  // Keyboard: Enter finishes, Escape cancels, Backspace removes last vertex.
  useEffect(() => {
    if (!drawing || zonePlacing) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancelDrawing()
      else if (e.key === 'Enter') finish(vertices)
      else if (e.key === 'Backspace') setVertices((v) => v.slice(0, -1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const handleClick = (e: MapLayerMouseEvent) => {
    setMenu(null)
    setPalette(null)
    // Only placing mode sets the center; other clicks never create a zone.
    if (zonePlacing) {
      onZonePlace([e.lngLat.lng, e.lngLat.lat])
      return
    }
    if (mode === 'region') {
      // Geometry comes from the full collection in App: rendered features are tile-clipped.
      const rid = e.features?.[0]?.properties.rid
      if (rid) onRegionClick(rid)
      return
    }
    if (!drawing) {
      const feature = e.features?.[0]
      if (feature?.layer.id === 'poi-circle') {
        setPoiId(feature.properties.id)
        return
      }
      if (feature?.layer.id === 'edit-handles') return
      // Administrative regions are fixed boundaries: they can be deleted but not edited.
      const editable = feature?.layer.id === 'aoi-fill' && feature.properties.kind !== 'region'
      setSelectedId(editable ? feature.properties.id : null)
      return
    }
    const p: LngLat = [e.lngLat.lng, e.lngLat.lat]
    if (mode === 'rectangle') {
      if (vertices.length === 0) setVertices([p])
      else if (pixelDistance(p, vertices[0]) >= DUPLICATE_PX) onShapeComplete('rectangle', rectangleFrom(vertices[0], p))
      return
    }
    if (vertices.length >= 3 && pixelDistance(p, vertices[0]) < CLOSE_PX) {
      finish(vertices)
      return
    }
    const last = vertices[vertices.length - 1]
    if (last && pixelDistance(p, last) < DUPLICATE_PX) return
    setVertices((v) => [...v, p])
  }

  const handleDblClick = (e: MapLayerMouseEvent) => {
    if (!drawing) return
    e.preventDefault()
    finish(vertices)
  }

  const handleMouseMove = (e: MapLayerMouseEvent) => {
    if (zonePlacing) {
      onHover(null)
      return
    }
    if (drag && selected) {
      const p: LngLat = [e.lngLat.lng, e.lngLat.lat]
      let coords: LngLat[]
      if (drag.kind === 'vertex') {
        coords =
          selected.kind === 'rectangle'
            ? resizeCorner(drag.origin, drag.index, p)
            : drag.origin.map((c, i) => (i === drag.index ? p : c))
      } else if (drag.kind === 'edge') {
        coords = resizeEdge(drag.origin, drag.index, drag.start, p)
      } else if (drag.kind === 'rotate') {
        coords = rotate(drag.origin, drag.center, angleFrom(drag.center, p) - drag.startAngle)
      } else {
        const [dx, dy] = [p[0] - drag.start[0], p[1] - drag.start[1]]
        coords = drag.origin.map(([x, y]) => [x + dx, y + dy])
      }
      onUpdate(selected.id, coords)
      return
    }
    if (mode === 'region') {
      const rid: string | null = e.features?.[0]?.properties.rid ?? null
      if (rid !== hoverRegion) {
        setHoverRegion(rid)
        onHoverRegion(rid)
      }
      onHover(null)
      return
    }
    if (drawing) {
      setCursor([e.lngLat.lng, e.lngLat.lat])
      onHover(null)
      return
    }
    const top = e.features?.[0]
    if (top?.layer.id === 'poi-circle') {
      mapRef.current?.getMap().dragPan.enable()
      setHoverHandle(null)
      setMapCursor('pointer')
      onHover(null)
      return
    }
    const handle = top?.layer.id === 'edit-handles' ? (top.properties as HandleProps) : null
    const fill = e.features?.find((f) => isAoiFill(f.layer.id))
    const overSelected = !!fill && fill.properties.id === selectedId

    // Disable map panning over editable parts, so pressing there edits the shape, not the map.
    const dragPan = mapRef.current?.getMap().dragPan
    if (handle || overSelected) dragPan?.disable()
    else dragPan?.enable()

    setHoverHandle(handle?.key ?? null)
    setMapCursor(handle ? handleCursor(handle) : overSelected ? 'grab' : fill ? 'pointer' : '')
    onHover(fill?.properties.id ?? null)
  }

  const handlesGeo = useMemo<FeatureCollection>(() => {
    if (!selected || selected.kind === 'region') return { type: 'FeatureCollection', features: [] }
    const coords = selected.coords
    const point = (kind: HandleProps['kind'], index: number, coordinates: LngLat) => ({
      type: 'Feature' as const,
      properties: { kind, index, key: `${kind}${index}` },
      geometry: { type: 'Point' as const, coordinates },
    })
    const mid = (i: number): LngLat => {
      const [a, b] = [coords[i], coords[(i + 1) % coords.length]]
      return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
    }
    const [stemBase, rotatePos] = rotateHandle(
      coords,
      selected.kind,
      drag?.kind === 'rotate' ? drag.anchorIndex : undefined,
    )
    return {
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [stemBase, rotatePos] } },
        ...coords.map((c, i) => point('vertex', i, c)),
        // Polygons: midpoints add vertices. Rectangles: side handles resize one side.
        ...coords.map((_, i) => point(selected.kind === 'polygon' ? 'mid' : 'edge', i, mid(i))),
        point('rotate', 0, rotatePos),
      ],
    }
  }, [selected, drag])

  const toCollection = (list: AoiPolygon[]): FeatureCollection => ({
    type: 'FeatureCollection',
    features: list.map((p) => ({
      type: 'Feature',
      properties: { id: p.id, name: p.name, kind: p.kind },
      geometry: shapeGeometry(p),
    })),
  })

  // Editable shapes change on every drag frame; administrative regions never change after being added.
  // Keeping them in separate sources means a drag re-tiles only the small shapes, not large boundaries.
  const polygonsGeo = useMemo(() => toCollection(polygons.filter((p) => p.kind !== 'region')), [polygons])
  const regionKey = polygons
    .filter((p) => p.kind === 'region')
    .map((p) => p.id)
    .join('|')
  const regionsGeo = useMemo(
    () => toCollection(polygons.filter((p) => p.kind === 'region')),
    [regionKey], // eslint-disable-line react-hooks/exhaustive-deps
  )

  const previewGeo = useMemo<FeatureCollection>(
    () => ({
      type: 'FeatureCollection',
      features: previewGeometry ? [{ type: 'Feature', properties: {}, geometry: previewGeometry }] : [],
    }),
    [previewGeometry],
  )

  const sketchGeo = useMemo<FeatureCollection>(() => {
    if (mode === 'rectangle' && vertices.length === 1 && cursor) {
      const ring = rectangleFrom(vertices[0], cursor)
      return {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: {},
            geometry: { type: 'LineString', coordinates: [...ring, ring[0]] },
          },
          { type: 'Feature', properties: { first: true }, geometry: { type: 'Point', coordinates: vertices[0] } },
        ],
      }
    }
    const line = cursor ? [...vertices, cursor] : vertices
    return {
      type: 'FeatureCollection',
      features: [
        ...(line.length >= 2
          ? [{ type: 'Feature' as const, properties: {}, geometry: { type: 'LineString' as const, coordinates: line } }]
          : []),
        ...vertices.map((v, i) => ({
          type: 'Feature' as const,
          properties: { first: i === 0 },
          geometry: { type: 'Point' as const, coordinates: v },
        })),
      ],
    }
  }, [mode, vertices, cursor])

  // Zoomed out, each square collapses into a pin. Hysteresis band avoids flicker at the threshold.
  // Ids listed here render as a full square; every other zone is a pin.
  const [zoneExpanded, setZoneExpanded] = useState<Set<string>>(() => new Set())
  const zoneDraggedRef = useRef(false)
  const updateZoneCompact = () => {
    const map = mapRef.current?.getMap()
    if (!map) return
    setZoneExpanded((prev) => {
      const next = new Set<string>()
      for (const zone of zones) {
        const [w, s, e, n] = zoneBbox(zone)
        const sw = map.project([w, s])
        const ne = map.project([e, n])
        const side = Math.min(Math.abs(ne.x - sw.x), Math.abs(sw.y - ne.y))
        if (side >= (prev.has(zone.id) ? ZONE_SQUARE_HIDE_PX : ZONE_SQUARE_SHOW_PX)) next.add(zone.id)
      }
      // Keep the same Set when nothing changed so React skips the re-render.
      return next.size === prev.size && [...next].every((id) => prev.has(id)) ? prev : next
    })
  }
  useEffect(updateZoneCompact, [zones]) // eslint-disable-line react-hooks/exhaustive-deps
  const selectedZone = zones.find((z) => z.id === selectedZoneId && zoneExpanded.has(z.id)) ?? null
  const zoneCornerList = useMemo(() => (selectedZone ? zoneCorners(selectedZone) : []), [selectedZone])
  const zoneGeo = useMemo<FeatureCollection>(
    () => ({
      type: 'FeatureCollection',
      features: zones
        .filter((z) => zoneExpanded.has(z.id))
        .map((z) => {
          const corners = zoneCorners(z)
          return {
            type: 'Feature' as const,
            properties: { id: z.id, selected: z.id === selectedZoneId },
            geometry: { type: 'Polygon' as const, coordinates: [[...corners, corners[0]]] },
          }
        }),
    }),
    [zones, zoneExpanded, selectedZoneId],
  )
  // A drag on a pin or center marker also ends in a click; that click is ignored.
  const consumeZoneDrag = () => {
    if (!zoneDraggedRef.current) return false
    zoneDraggedRef.current = false
    return true
  }
  const markZoneDragStart = () => {
    zoneDraggedRef.current = true
  }
  // Clear the flag after the trailing click (if any) so the next real click is not swallowed.
  const markZoneDragEnd = () => {
    setTimeout(() => {
      zoneDraggedRef.current = false
    }, 0)
  }

  // Camera report for the automatic admin level. Fires on load and after every pan or zoom.
  const reportView = (e: { target: MaplibreMap }) => {
    const c = e.target.getCenter()
    onViewChange({ zoom: e.target.getZoom(), center: [c.lng, c.lat] })
    const b = e.target.getBounds()
    setFootView([Math.max(-180, b.getWest()), b.getSouth(), Math.min(180, b.getEast()), b.getNorth()])
  }

  return (
    <>
    <Map
      ref={mapRef}
      initialViewState={{ longitude: -74, latitude: 4.6, zoom: 4 }}
      style={{ width: '100%', height: '100%' }}
      mapStyle={basemap}
      attributionControl={false}
      cursor={
        mode === 'region'
          ? hoverRegion
            ? 'pointer'
            : ''
          : drawing
            ? 'crosshair'
            : drag?.kind === 'shape'
              ? 'grabbing'
              : mapCursor
      }
      doubleClickZoom={!drawing}
      onClick={handleClick}
      onDblClick={handleDblClick}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseOut={() => {
        onHover(null)
        setHoverHandle(null)
        if (hoverRegion) {
          setHoverRegion(null)
          onHoverRegion(null)
        }
      }}
      onContextMenu={handleContextMenu}
      onMoveStart={() => {
        cancelPreload() // visible tiles of the new view go first
        setMenu(null)
        setPalette(null)
      }}
      onMove={(e) => {
        updateZoneCompact()
        setZoomLevel(Math.floor(e.viewState.zoom))
      }}
      onLoad={(e) => {
        reportView(e)
        updateZoneCompact()
        setZoomLevel(Math.floor(e.target.getZoom()))
      }}
      onError={(e) => {
        const src = (e as unknown as { sourceId?: string }).sourceId
        if (!src || !OVERLAY_SOURCES.has(src)) console.error(e.error)
      }}
      onMoveEnd={reportView}
      onIdle={(e) => {
        // Overlay tiles that failed (GIBS/CMR errors) are refetched once the map is idle; only
        // tiles still in view are reloaded.
        for (const { id, tiles } of takeFailedTiles())
          if (e.target.getSource(`ov-${id}`)) e.target.refreshTiles(`ov-${id}`, tiles)
      }}
      interactiveLayerIds={
        mode === 'region'
          ? // Only layers that exist can be queried; subdivisions sit above countries.
            [
              ...(regionSubdivisions ? ['region-sub-fill'] : []),
              ...(regionCountries ? ['region-countries-fill'] : []),
            ]
          : drawing
            ? []
            : ['poi-circle', 'edit-handles', 'aoi-fill', 'aoi-region-fill']
      }
    >
      {/* OSM license requires attribution; kept bottom-left so the right corner is free for InfoBox. */}
      <AttributionControl position="bottom-left" compact />
      {/* Region picker layers; beforeId keeps them under the AOI shapes even when mounted later. */}
      {mode === 'region' && regionCountries && (
        <Source id="region-countries" type="geojson" data={regionCountries} promoteId="rid">
          <Layer
            id="region-countries-fill"
            type="fill"
            beforeId="aoi-region-fill"
            paint={{
              'fill-color': '#7c3aed',
              'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.25, 0.03],
            }}
          />
          <Layer
            id="region-countries-line"
            type="line"
            beforeId="aoi-region-fill"
            paint={{ 'line-color': '#7c3aed', 'line-width': 1 }}
          />
        </Source>
      )}
      {mode === 'region' && regionSubdivisions && (
        <Source id="region-sub" type="geojson" data={regionSubdivisions} promoteId="rid">
          <Layer
            id="region-sub-fill"
            type="fill"
            beforeId="aoi-region-fill"
            paint={{
              'fill-color': '#7c3aed',
              'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.25, 0.03],
            }}
          />
          <Layer
            id="region-sub-line"
            type="line"
            beforeId="aoi-region-fill"
            paint={{ 'line-color': '#7c3aed', 'line-width': 0.8 }}
          />
        </Source>
      )}
      {/* Search preview outline. Declared before the AOI sources so it draws underneath them. */}
      <Source id="aoi-preview" type="geojson" data={previewGeo}>
        <Layer id="preview-fill" type="fill" paint={{ 'fill-color': '#0ea5e9', 'fill-opacity': 0.1 }} />
        <Layer
          id="preview-line"
          type="line"
          paint={{ 'line-color': '#0ea5e9', 'line-width': 2, 'line-dasharray': [2, 2] }}
        />
      </Source>
      {/* Place names inside the study areas (stand-in for the hidden raster labels); never block clicks. */}
      {areaPlaces
        ?.filter((p) => zoomLevel >= PLACE_MINZOOM[p.rank])
        .map((p) => (
          <Marker key={p.id} longitude={p.lon} latitude={p.lat} anchor="center" style={{ pointerEvents: 'none' }}>
            <span className={`area-place area-place-${p.rank}`}>{p.name}</span>
          </Marker>
        ))}
      {!drawing &&
        featureLabels.map((f) => {
          const on = activeFeature?.name === f.name
          return (
            <Marker key={`${f.category}:${f.name}`} longitude={f.lon} latitude={f.lat} anchor="left">
              <span className={`feature-label${on ? ' is-active' : ''}`}>
                <button
                  type="button"
                  className="feature-label-main"
                  title={`${f.category_name}: ir a ${f.name}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    onFeatureClick(f)
                  }}
                >
                  <span className="feature-dot" style={{ background: CATEGORY_COLOR[f.category] }} aria-hidden="true" />
                  {f.name}
                </button>
                {on && (
                  <button
                    type="button"
                    className="feature-label-add"
                    title="Agregar como área de estudio"
                    aria-label={`Agregar ${f.name} como área de estudio`}
                    onClick={(e) => {
                      e.stopPropagation()
                      onFeatureAdd(f)
                    }}
                  >
                    <Plus size={14} aria-hidden="true" /> Área
                  </button>
                )}
              </span>
            </Marker>
          )
        })}
      {/* Land-cover mask: declared before the AOI source so the AOI outline and fill draw over it. */}
      {coverMask && (
        <Source id="cover-mask" type="image" url={coverMask.url} coordinates={coverMask.bounds}>
          <Layer
            id="cover-mask-layer"
            type="raster"
            paint={{ 'raster-opacity': 0.7, 'raster-resampling': 'nearest' }}
          />
        </Source>
      )}
      <Source id="aoi-regions" type="geojson" data={regionsGeo}>
        {/* Study areas only bound the search: near-transparent fill (kept for hit-testing) and a dashed outline. */}
        <Layer id="aoi-region-fill" type="fill" paint={{ 'fill-color': '#ff7a00', 'fill-opacity': 0.04 }} />
        <Layer
          id="aoi-region-outline"
          type="line"
          paint={{ 'line-color': '#ff7a00', 'line-width': 2, 'line-dasharray': [3, 2] }}
        />
      </Source>
      {/* Water overlays sit under the AOI shapes; mounted after aoi-regions so beforeId exists. */}
      {OVERLAY_IDS.filter((id) => overlays[id].on).map((id) => {
        const base = overlayTiles(id, overlays[id].date)
        const mode = id === 'nisar' ? overlays[id].mode ?? 'color' : undefined
        const url = mode
          ? `${NISAR_PROTOCOL}://${mode}/${nisarDate(overlays[id].date)}/${nisarDirs}/{z}/{x}/{y}`
          : id === 'dswx'
            ? `${DSWX_PROTOCOL}://${overlays[id].date}/{z}/{x}/{y}`
            : base
        const opacity = overlays[id].opacity / 100
        // NISAR fades in from NISAR_FADE_START to NISAR_FADE_END while the swath outline fades out.
        const imgOpacity = mode
          ? (['interpolate', ['linear'], ['zoom'], NISAR_FADE_START, 0, NISAR_FADE_END, opacity] as unknown as number)
          : opacity
        // 'color' mode tones down speckle, stripes and hard swath edges of the false-color preview.
        const paint =
          mode === 'color'
            ? {
                'raster-opacity': imgOpacity,
                'raster-contrast': -0.2,
                'raster-saturation': -0.25,
                'raster-resampling': 'linear' as const,
                'raster-fade-duration': 100,
              }
            : { 'raster-opacity': imgOpacity, 'raster-fade-duration': 100 }
        return (
          // Keyed by layer only: a new tile URL (date, mode, passes) goes through setTiles, so the
          // old tiles stay on screen until the new ones load.
          <Fragment key={id}>
          {mode && showFoot && (
            <Source id="ov-nisar-outline" type="geojson" data={nisarFoot}>
              <Layer
                id="ov-nisar-outline-layer"
                type="line"
                beforeId="aoi-region-fill"
                maxzoom={NISAR_OUTLINE_MAXZOOM}
                filter={['in', ['get', 'dir'], ['literal', nisarDirs.split('')]]}
                paint={{
                  'line-color': ['match', ['get', 'dir'], 'A', NISAR_ASC_COLOR, NISAR_DESC_COLOR],
                  'line-width': 1.2,
                  'line-opacity': ['interpolate', ['linear'], ['zoom'], NISAR_FADE_START, opacity, NISAR_FADE_END, 0],
                }}
              />
            </Source>
          )}
          <Source
            id={`ov-${id}`}
            type="raster"
            tiles={[url]}
            tileSize={256}
            maxzoom={OVERLAYS[id].maxzoom}
            attribution={OVERLAYS[id].attribution}
          >
            <Layer
              id={`ov-${id}-layer`}
              type="raster"
              beforeId="aoi-region-fill"
              minzoom={mode ? NISAR_FADE_START : 0}
              paint={paint}
            />
          </Source>
          </Fragment>
        )
      })}
      <Source id="aoi-polygons" type="geojson" data={polygonsGeo}>
        <Layer id="aoi-fill" type="fill" paint={{ 'fill-color': '#ff7a00', 'fill-opacity': 0.04 }} />
        <Layer
          id="aoi-outline"
          type="line"
          paint={{
            'line-color': ['case', ['==', ['get', 'id'], selectedId ?? ''], '#0078ff', '#ff7a00'],
            'line-width': ['case', ['==', ['get', 'id'], selectedId ?? ''], 3, 2],
            'line-dasharray': [3, 2],
          }}
        />
      </Source>
      {/* Point of interest square: above study areas and overlays, under labels, POIs and edit handles. */}
      <Source id="user-zone" type="geojson" data={zoneGeo}>
        <Layer
          id="zone-fill"
          type="fill"
          paint={{
            'fill-color': '#db2777',
            'fill-opacity': ['case', ['boolean', ['get', 'selected'], false], 0.3, 0.16],
          }}
        />
        <Layer
          id="zone-outline"
          type="line"
          paint={{
            'line-color': ['case', ['boolean', ['get', 'selected'], false], '#9d174d', '#db2777'],
            'line-width': ['case', ['boolean', ['get', 'selected'], false], 3, 2],
          }}
        />
      </Source>
      {zones.map((zone) => {
        const title = zone.note ? `${zone.name ?? ''}: ${zone.note}` : zone.name
        const selected = zone.id === selectedZoneId
        const moveCenter = (e: { lngLat: { lng: number; lat: number } }) =>
          onZoneChange({ ...zone, center: [e.lngLat.lng, e.lngLat.lat] })
        // Zoomed out: a pin stands in for the square. Drag moves the center, click selects and zooms to the square.
        if (!zoneExpanded.has(zone.id))
          return (
            <Marker
              key={zone.id}
              longitude={zone.center[0]}
              latitude={zone.center[1]}
              anchor="bottom"
              draggable={!zonePlacing}
              onDragStart={markZoneDragStart}
              onDrag={moveCenter}
              onDragEnd={markZoneDragEnd}
              onClick={(e) => {
                e.originalEvent.stopPropagation()
                // A drag also ends in a click on the pin; only a plain click zooms.
                if (consumeZoneDrag()) return
                onSelectZone(zone.id)
                const [w, s, e2, n] = zoneBbox(zone)
                mapRef.current?.getMap().fitBounds([w, s, e2, n], { padding: 60, duration: 800 })
              }}
            >
              <div className={selected ? 'zone-pin zone-pin-selected' : 'zone-pin'} title={title}>
                <svg width="26" height="34" viewBox="0 0 26 34" aria-hidden="true">
                  <path
                    d="M13 1C6.4 1 1 6.3 1 12.8 1 21.6 13 33 13 33s12-11.4 12-20.2C25 6.3 19.6 1 13 1z"
                    fill={selected ? '#9d174d' : '#db2777'}
                    stroke="#9d174d"
                    strokeWidth="1.5"
                  />
                  <circle cx="13" cy="13" r="4.5" fill="#ffffff" />
                </svg>
                {zone.name && <span className="zone-label zone-pin-label">{zone.name}</span>}
              </div>
            </Marker>
          )
        // Dragging the center moves the square; the range is kept.
        return (
          <Marker
            key={zone.id}
            longitude={zone.center[0]}
            latitude={zone.center[1]}
            anchor="center"
            draggable={!zonePlacing}
            onDragStart={markZoneDragStart}
            onDrag={moveCenter}
            onDragEnd={markZoneDragEnd}
            onClick={(e) => {
              e.originalEvent.stopPropagation()
              if (consumeZoneDrag()) return
              onSelectZone(zone.id)
            }}
          >
            <div className={selected ? 'zone-center zone-center-selected' : 'zone-center'} title={title}>
              <span className="zone-center-dot" />
              {zone.name && <span className="zone-label">{zone.name}</span>}
            </div>
          </Marker>
        )
      })}
      {/* Dragging a corner of the selected square resizes it around the fixed center. */}
      {selectedZone &&
        zoneCornerList.map((c, i) => (
          <Marker
            key={`${selectedZone.id}-${i}`}
            longitude={c[0]}
            latitude={c[1]}
            anchor="center"
            draggable={!zonePlacing}
            onDrag={(e) =>
              onZoneChange({
                ...selectedZone,
                halfSizeKm: halfKmFromCorner(selectedZone.center, [e.lngLat.lng, e.lngLat.lat]),
              })
            }
          >
            <span className={`zone-corner zone-corner-${i}`} />
          </Marker>
        ))}
      <Source id="pois" type="geojson" data={poisGeo}>
        <Layer
          id="poi-circle"
          type="circle"
          paint={{
            // Selected POI: bigger, with a thick dark ring.
            'circle-radius': ['case', ['==', ['get', 'id'], poiId ?? ''], 11, 7],
            'circle-color': [
              'match',
              ['get', 'category'],
              ...Object.entries(POI_COLOR).flat(),
              '#6b7280',
            ] as unknown as string,
            'circle-stroke-color': ['case', ['==', ['get', 'id'], poiId ?? ''], '#111827', '#ffffff'],
            'circle-stroke-width': ['case', ['==', ['get', 'id'], poiId ?? ''], 3.5, 2],
          }}
        />
      </Source>
      {/* Place-name labels above overlays and AOI shapes, under POIs and edit handles. */}
      {/* No fade: cross-fading parent/child label tiles while zooming shows names twice. */}
      {/* With study areas the raster labels are hidden: names outside the areas cannot be removed from a raster. */}
      {areaPlaces === null && (!labels.withOverlaysOnly || OVERLAY_IDS.some((id) => overlays[id].on)) && (
        <Source id="basemap-labels" key={labels.tiles} type="raster" tiles={[labels.tiles]} tileSize={256} maxzoom={labels.maxzoom}>
          <Layer
            id="basemap-labels-layer"
            type="raster"
            beforeId="poi-circle"
            paint={{ 'raster-opacity': 1, 'raster-fade-duration': 0 }}
          />
        </Source>
      )}
      <Source id="aoi-edit-handles" type="geojson" data={handlesGeo}>
        <Layer
          id="edit-rotate-stem"
          type="line"
          filter={['==', '$type', 'LineString']}
          paint={{ 'line-color': '#16a34a', 'line-width': 1.5, 'line-dasharray': [2, 2] }}
        />
        <Layer
          id="edit-handles"
          type="circle"
          filter={['==', '$type', 'Point']}
          paint={{
            'circle-radius': [
              'case',
              ['==', ['get', 'key'], hoverHandle ?? ''],
              ['match', ['get', 'kind'], 'mid', 6, 'edge', 7, 'rotate', 9, 8],
              ['match', ['get', 'kind'], 'mid', 4, 'edge', 5, 'rotate', 7, 6],
            ],
            'circle-color': [
              'case',
              ['==', ['get', 'key'], hoverHandle ?? ''],
              ['match', ['get', 'kind'], 'rotate', '#15803d', '#0078ff'],
              ['match', ['get', 'kind'], 'rotate', '#22c55e', '#ffffff'],
            ],
            'circle-opacity': ['match', ['get', 'kind'], 'mid', 0.7, 1],
            'circle-stroke-color': ['match', ['get', 'kind'], 'rotate', '#ffffff', '#0078ff'],
            'circle-stroke-width': 2,
            'circle-stroke-opacity': ['match', ['get', 'kind'], 'mid', 0.7, 1],
          }}
        />
      </Source>
      <Source id="aoi-sketch" type="geojson" data={sketchGeo}>
        <Layer
          id="sketch-line"
          type="line"
          filter={['==', '$type', 'LineString']}
          paint={{ 'line-color': '#0078ff', 'line-width': 2, 'line-dasharray': [2, 2] }}
        />
        <Layer
          id="sketch-vertices"
          type="circle"
          filter={['==', '$type', 'Point']}
          paint={{
            'circle-radius': ['case', ['get', 'first'], 6, 4],
            'circle-color': '#ffffff',
            'circle-stroke-color': '#0078ff',
            'circle-stroke-width': 2,
          }}
        />
      </Source>
      {palette && (
        <div
          ref={paletteRef}
          className="map-toolbar"
          role="toolbar"
          aria-label="Herramientas de dibujo"
          style={{ left: palette.x, top: palette.y }}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          onContextMenu={(e) => {
            e.preventDefault()
            e.stopPropagation()
          }}
        >
          {TOOLS.map((t) => (
            <button
              key={t.mode}
              type="button"
              title={t.label}
              aria-label={t.label}
              aria-pressed={mode === t.mode}
              onClick={() => {
                onSelectMode(t.mode)
                setPalette(null)
              }}
            >
              <t.Icon size={16} aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
      {menu && (
        <div className="context-menu" style={{ left: menu.x, top: menu.y }} onContextMenu={(e) => e.preventDefault()}>
          <div className="context-menu-title">{menu.name}</div>
          <button
            onClick={() => {
              onDelete(menu.id)
              setMenu(null)
            }}
          >
            <Trash2 size={16} />
            Eliminar
          </button>
        </div>
      )}
    </Map>
    {poi && <PoiPanel poi={poi} start={searchStart} end={searchEnd} onClose={() => setPoiId(null)} />}
    </>
  )
}
