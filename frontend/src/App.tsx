import { useState } from 'react'
import MapView from './components/MapView'
import PolygonPanel from './components/PolygonPanel'
import InfoBox from './components/InfoBox'
import ShapeInfo from './components/ShapeInfo'
import ToolInfo from './components/ToolInfo'
import SearchBar from './components/SearchBar'
import { useRegionPicker } from './useRegionPicker'
import type { MapViewport } from './useRegionPicker'
import type { BBox, PlaceResult } from './nominatim'
import type { AoiPolygon, DrawMode, LngLat, RegionGeometry } from './types'

const LABELS: Record<DrawMode, string> = { polygon: 'Polígono', rectangle: 'Rectángulo', region: 'Región' }

export default function App() {
  const [polygons, setPolygons] = useState<AoiPolygon[]>([])
  const [mode, setMode] = useState<DrawMode | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [hoveredTool, setHoveredTool] = useState<DrawMode | null>(null)
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null)
  // Search: last result picked (dashed outline) and the camera target for it.
  const [preview, setPreview] = useState<PlaceResult | null>(null)
  const [flyTo, setFlyTo] = useState<{ bbox: BBox; key: number } | null>(null)
  // Same start as MapView's initialViewState; replaced on map load and after each move.
  const [view, setView] = useState<MapViewport>({ zoom: 4, center: [-74, 4.6] })
  const regions = useRegionPicker(mode === 'region', view)
  const hovered = polygons.find((p) => p.id === hoveredId)
  const deletePolygon = (id: string) => setPolygons((prev) => prev.filter((p) => p.id !== id))

  const addShape = (kind: DrawMode, coords: LngLat[], name?: string, geometry?: RegionGeometry) => {
    setPolygons((prev) => [
      ...prev,
      { id: crypto.randomUUID(), name: name ?? `${LABELS[kind]} ${prev.length + 1}`, kind, coords, geometry },
    ])
    setMode(null)
  }

  const findRegion = (rid: string) =>
    (rid.startsWith('s:') ? regions.subdivisions : regions.countries)?.features.find((f) => f.properties.rid === rid)

  // Countries are added directly at level ADM0; otherwise clicking a country loads its subdivisions.
  const handleRegionClick = (rid: string) => {
    const f = findRegion(rid)
    if (!f) return
    if (rid.startsWith('s:') || regions.level === 'ADM0') {
      const name = rid.startsWith('s:') ? `${f.properties.name} (${regions.country?.name})` : f.properties.name
      addShape('region', [], name, f.geometry)
    } else {
      regions.pickCountry(f.properties.iso, f.properties.name)
    }
  }

  const regionHover = hoveredRegion ? findRegion(hoveredRegion) : undefined
  const regionHint = !regionHover
    ? ''
    : hoveredRegion!.startsWith('s:') || regions.level === 'ADM0'
      ? 'Clic para agregarla como área de estudio.'
      : 'Clic para ver sus subdivisiones.'

  return (
    <div className="app">
      <MapView
        polygons={polygons}
        mode={mode}
        regionCountries={mode === 'region' ? regions.countries : null}
        regionSubdivisions={mode === 'region' ? regions.subdivisions : null}
        onShapeComplete={(kind, coords) => addShape(kind, coords)}
        onRegionClick={handleRegionClick}
        onHoverRegion={setHoveredRegion}
        onViewChange={setView}
        onCancelDrawing={() => setMode(null)}
        onDelete={deletePolygon}
        onHover={setHoveredId}
        onUpdate={(id, coords) => setPolygons((prev) => prev.map((p) => (p.id === id ? { ...p, coords } : p)))}
        previewGeometry={preview?.geometry ?? null}
        flyToBbox={flyTo}
      />
      <SearchBar
        onPreview={(r) => {
          setPreview(r)
          setFlyTo((prev) => ({ bbox: r.bbox, key: (prev?.key ?? 0) + 1 }))
        }}
        onAdd={(r) => {
          if (!r.geometry) return
          addShape('region', [], r.name, r.geometry)
          setPreview(null)
        }}
      />
      <PolygonPanel
        polygons={polygons}
        mode={mode}
        regions={regions}
        onSelectMode={(m) => setMode((current) => (current === m ? null : m))}
        onDelete={deletePolygon}
        onHoverTool={setHoveredTool}
      />
      {hoveredTool ? (
        <InfoBox>
          <ToolInfo tool={hoveredTool} />
        </InfoBox>
      ) : regionHover ? (
        <InfoBox>
          <h3>{regionHover.properties.name}</h3>
          <p className="info-hint">{regionHint}</p>
        </InfoBox>
      ) : (
        hovered && (
          <InfoBox>
            <ShapeInfo shape={hovered} />
          </InfoBox>
        )
      )}
    </div>
  )
}
