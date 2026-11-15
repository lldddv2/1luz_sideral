import { useMemo, useState } from "react";
import MapView from "./components/MapView";
import Sidebar from "./components/Sidebar";
import InfoBox from "./components/InfoBox";
import ShapeInfo from "./components/ShapeInfo";
import AcquisitionTimeline from "./components/AcquisitionTimeline";
import ToolInfo from "./components/ToolInfo";
import SearchBar from "./components/SearchBar";
import CoverChips from "./components/CoverChips";
import { useLandcover } from "./useLandcover";
import { useRegionPicker } from "./useRegionPicker";
import type { MapViewport } from "./useRegionPicker";
import { useDownload } from "./useDownload";
import { useAreaPlaces } from "./areaPlaces";
import { usePasses } from "./usePasses";
import type { BBox, PlaceResult } from "./nominatim";
import { aoiBoxes, aoiGeometries, fetchOutline, groupLabel, inShapes } from "./features";
import type { NaturalFeature } from "./features";
import type { AoiPolygon, DownloadTarget, DrawMode, LngLat, RegionGeometry, UserZone } from "./types";
import { ZONE_DEFAULT_HALF_KM, zoneBbox, zoneGeometry, zoneLabel } from "./zone";
import { BASEMAPS } from "./basemaps";
import type { BasemapId } from "./basemaps";
import { DEFAULT_OVERLAYS } from "./layers";
import type { OverlayId, OverlayState } from "./layers";

const LABELS: Record<DrawMode, string> = {
  polygon: "Polígono",
  rectangle: "Rectángulo",
  region: "Región",
};

export default function App() {
  const [polygons, setPolygons] = useState<AoiPolygon[]>([]);
  const [mode, setMode] = useState<DrawMode | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [hoveredTool, setHoveredTool] = useState<DrawMode | null>(null);
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null);
  const [basemap, setBasemap] = useState<BasemapId>("gray");
  const [overlays, setOverlays] = useState(DEFAULT_OVERLAYS);
  const changeOverlay = (id: OverlayId, patch: Partial<OverlayState>) =>
    setOverlays((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  // Search: last result picked (dashed outline) and the camera target for it.
  const [preview, setPreview] = useState<PlaceResult | null>(null);
  // Natural features labelled on the map, and the one last picked.
  const [labels, setLabels] = useState<NaturalFeature[]>([]);
  const [feature, setFeature] = useState<NaturalFeature | null>(null);
  const [flyTo, setFlyTo] = useState<{ bbox: BBox; key: number } | null>(null);
  // Same start as MapView's initialViewState; replaced on map load and after each move.
  const [view, setView] = useState<MapViewport>({
    zoom: 4,
    center: [-74, 4.6],
  });
  const regions = useRegionPicker(mode === "region", view);
  // Points of interest: user-placed centers, each with its own square range; annotation only.
  const [zones, setZones] = useState<UserZone[]>([]);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [zonePlacing, setZonePlacing] = useState(false);
  const toggleZonePlacing = () => {
    setMode(null);
    setZonePlacing((on) => !on);
  };
  // Each click in placing mode adds a new point and selects it; placing mode then ends.
  const placeZone = (center: LngLat) => {
    setZonePlacing(false);
    const id = crypto.randomUUID();
    setZones((prev) => [...prev, { id, center, halfSizeKm: ZONE_DEFAULT_HALF_KM }]);
    setSelectedZoneId(id);
  };
  const changeZone = (zone: UserZone) => setZones((prev) => prev.map((z) => (z.id === zone.id ? zone : z)));
  const deleteZone = (id: string) => {
    setZones((prev) => prev.filter((z) => z.id !== id));
    setSelectedZoneId((sel) => (sel === id ? null : sel));
  };
  const focusZone = (id: string) => {
    const zone = zones.find((z) => z.id === id);
    if (!zone) return;
    const bbox = zoneBbox(zone);
    setFlyTo((prev) => ({ bbox, key: (prev?.key ?? 0) + 1 }));
  };
  // With study areas, the search and the map labels keep only features that meet them.
  const areaBoxes = useMemo(() => aoiBoxes(polygons), [polygons]);
  const areaShapes = useMemo(() => aoiGeometries(polygons), [polygons]);
  // Map place names limited to the study areas (null without areas: raster labels stay).
  const areaPlaces = useAreaPlaces(areaShapes);
  // No study-area selection state exists, so the timeline and NISAR scenes act on the most recently added area.
  const active = polygons.at(-1) ?? null;
  // Study areas only scope searches; the download covers the square of the selected point of interest.
  const selectedIndex = zones.findIndex((z) => z.id === selectedZoneId);
  const selectedZone = selectedIndex >= 0 ? zones[selectedIndex] : null;
  // Keyed on the square alone, so renaming the point keeps the same geometry object and the run survives.
  const zoneSquare = useMemo(
    () => (selectedZone ? zoneGeometry(selectedZone) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedZone?.id, selectedZone?.center[0], selectedZone?.center[1], selectedZone?.halfSizeKm],
  );
  const downloadTarget = useMemo<DownloadTarget | null>(() => {
    if (!selectedZone || !zoneSquare) return null;
    const [w, s, e, n] = zoneBbox(selectedZone);
    const meets = areaBoxes.some((b) => w <= b[2] && b[0] <= e && s <= b[3] && b[1] <= n);
    return {
      id: selectedZone.id,
      name: zoneLabel(selectedZone, selectedIndex),
      sideKm: selectedZone.halfSizeKm * 2,
      geometry: zoneSquare,
      outsideStudy: areaBoxes.length > 0 && !meets,
    };
  }, [selectedZone, selectedIndex, zoneSquare, areaBoxes]);
  const download = useDownload(downloadTarget);
  const hovered = polygons.find((p) => p.id === hoveredId);
  // The timeline spans the Descarga dates; null while they are incomplete or reversed.
  const { start, end } = download.params;
  const range = useMemo(
    () => (download.datesOk ? { start, end } : null),
    [download.datesOk, start, end],
  );
  const passes = usePasses(polygons, range);
  const cover = useLandcover(polygons);
  const shownLabels = useMemo(
    () => (areaShapes.length && labels.length > 1 ? labels.filter((f) => inShapes(f, areaShapes)) : labels),
    [labels, areaShapes],
  );
  const deletePolygon = (id: string) =>
    setPolygons((prev) => prev.filter((p) => p.id !== id));
  // Same toggle for the sidebar buttons and the map tool palette: picking the active tool clears it.
  const selectMode = (m: DrawMode) => {
    setZonePlacing(false);
    setMode((current) => (current === m ? null : m));
  };

  const addShape = (
    kind: DrawMode,
    coords: LngLat[],
    name?: string,
    geometry?: RegionGeometry,
  ) => {
    setPolygons((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        name: name ?? `${LABELS[kind]} ${prev.length + 1}`,
        kind,
        coords,
        geometry,
      },
    ]);
    setMode(null);
  };

  const findRegion = (rid: string) =>
    (rid.startsWith("s:")
      ? regions.subdivisions
      : regions.countries
    )?.features.find((f) => f.properties.rid === rid);

  // Countries are added directly at level ADM0; otherwise clicking a country loads its subdivisions.
  const handleRegionClick = (rid: string) => {
    const f = findRegion(rid);
    if (!f) return;
    if (rid.startsWith("s:") || regions.level === "ADM0") {
      const name = rid.startsWith("s:")
        ? `${f.properties.name} (${regions.country?.name})`
        : f.properties.name;
      addShape("region", [], name, f.geometry);
    } else {
      regions.pickCountry(f.properties.iso, f.properties.name);
    }
  };

  const bboxRing = ([w, s, e, n]: BBox): LngLat[] => [
    [w, s],
    [e, s],
    [e, n],
    [w, n],
  ];
  const pickFeature = (f: NaturalFeature) => {
    setFeature(f);
    setPreview({
      id: f.name,
      name: f.name,
      label: f.name,
      type: f.category_name,
      bbox: f.bbox,
      geometry: {
        type: "Polygon",
        coordinates: [[...bboxRing(f.bbox), bboxRing(f.bbox)[0]]],
      },
    });
    setFlyTo((prev) => ({ bbox: f.bbox, key: (prev?.key ?? 0) + 1 }));
    // Swap the bbox for the simplified outline once it arrives (if still the picked one).
    fetchOutline(f.id)
      .then((geometry) =>
        setPreview((prev) => (prev?.id === f.name ? { ...prev, geometry } : prev)),
      )
      .catch(() => {});
  };
  // The study area follows the simplified outline; the bbox is only the fallback.
  const addFeature = (f: NaturalFeature) => {
    setPreview(null);
    fetchOutline(f.id)
      .then((geometry) => addShape("region", [], f.name, geometry))
      .catch(() => addShape("rectangle", bboxRing(f.bbox), f.name));
  };

  const regionHover = hoveredRegion ? findRegion(hoveredRegion) : undefined;
  const regionHint = !regionHover
    ? ""
    : hoveredRegion!.startsWith("s:") || regions.level === "ADM0"
      ? "Clic para agregarla como área de estudio."
      : "Clic para ver sus subdivisiones.";

  return (
    <div className="app">
      <Sidebar
        polygons={polygons}
        mode={mode}
        regions={regions}
        download={download}
        cover={cover}
        basemap={basemap}
        onSelectMode={selectMode}
        onDelete={deletePolygon}
        onHoverTool={setHoveredTool}
        onBasemapChange={setBasemap}
        overlays={overlays}
        onOverlayChange={changeOverlay}
        zones={zones}
        selectedZoneId={selectedZoneId}
        onSelectZone={setSelectedZoneId}
        zonePlacing={zonePlacing}
        onToggleZonePlacing={toggleZonePlacing}
        onZoneChange={changeZone}
        onFocusZone={focusZone}
        onDeleteZone={deleteZone}
      />
      <div className="map-area">
        <MapView
          basemap={BASEMAPS[basemap].style}
          labels={BASEMAPS[basemap].labels}
          areaPlaces={areaPlaces}
          polygons={polygons}
          mode={mode}
          onSelectMode={selectMode}
          regionCountries={mode === "region" ? regions.countries : null}
          regionSubdivisions={mode === "region" ? regions.subdivisions : null}
          onShapeComplete={(kind, coords) => addShape(kind, coords)}
          onRegionClick={handleRegionClick}
          onHoverRegion={setHoveredRegion}
          onViewChange={setView}
          onCancelDrawing={() => setMode(null)}
          onDelete={deletePolygon}
          onHover={setHoveredId}
          onUpdate={(id, coords) =>
            setPolygons((prev) =>
              prev.map((p) => (p.id === id ? { ...p, coords } : p)),
            )
          }
          previewGeometry={preview?.geometry ?? null}
          flyToBbox={flyTo}
          searchStart={download.params.start}
          searchEnd={download.params.end}
          overlays={overlays}
          coverMask={cover.mask}
          featureLabels={shownLabels}
          activeFeature={feature}
          onFeatureClick={pickFeature}
          onFeatureAdd={addFeature}
          zones={zones}
          selectedZoneId={selectedZoneId}
          onSelectZone={setSelectedZoneId}
          zonePlacing={zonePlacing}
          onZonePlace={placeZone}
          onZoneChange={changeZone}
          onCancelZone={() => setZonePlacing(false)}
        />
        <SearchBar
          start={download.params.start}
          end={download.params.end}
          onDatesChange={download.setDates}
          onPreview={(r) => {
            setPreview(r);
            setFlyTo((prev) => ({ bbox: r.bbox, key: (prev?.key ?? 0) + 1 }));
          }}
          onAdd={(r) => {
            if (!r.geometry) return;
            addShape("region", [], r.name, r.geometry);
            setPreview(null);
          }}
          coverSuggestions={cover.suggestions}
          onPickCover={cover.toggle}
          onPickFeature={pickFeature}
          onAddFeature={addFeature}
          areaShapes={areaShapes}
          onShowFeatures={(list) => {
            setLabels(list);
            if (list.length > 1) setFeature(null);
          }}
        />
        <CoverChips
          chips={cover.chips}
          loading={cover.maskLoading}
          error={cover.maskError}
          onRemove={cover.toggle}
          labels={
            shownLabels.length > 1
              ? {
                  name: groupLabel(shownLabels),
                  count: shownLabels.length,
                  onClear: () => setLabels([]),
                }
              : null
          }
        />
        {active && (
          <AcquisitionTimeline range={range} entry={passes} />
        )}
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
    </div>
  );
}
