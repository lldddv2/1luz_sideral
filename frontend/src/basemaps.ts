import type { StyleSpecification } from 'maplibre-gl'

export type BasemapId = 'gray' | 'osm' | 'hls' | 's2cloudless'

interface Basemap {
  id: BasemapId
  label: string
  hint: string
  style: StyleSpecification
  // Label-only tiles drawn above the overlays so place names stay readable.
  // withOverlaysOnly: the basemap already bakes in names, so only draw them when overlays hide it.
  labels: { tiles: string; maxzoom: number; withOverlaysOnly?: boolean }
}

// Raster basemaps only: NISAR overlays will be added on top later.
// Both providers are keyless (CARTO now requires an API key and was dropped).
export const BASEMAPS: Record<BasemapId, Basemap> = {
  gray: {
    id: 'gray',
    label: 'Esri Gris claro',
    hint: 'Neutro, deja resaltar las capas de radar',
    labels: {
      tiles: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
      maxzoom: 16,
    },
    style: {
      version: 8,
      sources: {
        esri: {
          type: 'raster',
          tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'],
          tileSize: 256,
          maxzoom: 16,
          attribution: 'Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors',
        },
      },
      layers: [{ id: 'esri-gray', type: 'raster', source: 'esri' }],
    },
  },
  osm: {
    id: 'osm',
    label: 'OpenStreetMap',
    hint: 'Mapa estándar con calles y lugares',
    // OSM has no label-only tiles; Esri boundaries and places is the keyless stand-in.
    labels: {
      tiles: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      maxzoom: 19,
      withOverlaysOnly: true,
    },
    style: {
      version: 8,
      sources: {
        osm: {
          type: 'raster',
          tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
          tileSize: 256,
          attribution: '© OpenStreetMap contributors',
        },
      },
      layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
    },
  },
  // Optical HLS is drawn as dated raster sources in MapView over a dark gray base, so a date
  // change swaps tiles without rebuilding the map style.
  hls: {
    id: 'hls',
    label: 'Óptico HLS',
    hint: 'Landsat + Sentinel-2 del día; compara con el agua NISAR',
    labels: {
      tiles: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      maxzoom: 19,
    },
    style: {
      version: 8,
      sources: {
        esri: {
          type: 'raster',
          tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'],
          tileSize: 256,
          maxzoom: 16,
          attribution: 'Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors',
        },
      },
      layers: [{ id: 'esri-dark', type: 'raster', source: 'esri' }],
    },
  },
  // EOX Sentinel-2 cloudless: one cloud-free annual mosaic (keyless), not tied to any date.
  s2cloudless: {
    id: 's2cloudless',
    label: 'Óptico sin nubes',
    hint: 'Sentinel-2 2025, mosaico anual, no es de la fecha',
    labels: {
      tiles: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      maxzoom: 19,
    },
    style: {
      version: 8,
      sources: {
        eox: {
          type: 'raster',
          tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2025_3857/default/g/{z}/{y}/{x}.jpg'],
          tileSize: 256,
          attribution:
            'Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2025)',
        },
      },
      layers: [{ id: 's2cloudless', type: 'raster', source: 'eox' }],
    },
  },
}

export const BASEMAP_IDS: BasemapId[] = ['gray', 'osm', 'hls', 's2cloudless']

// HLS optical imagery from NASA GIBS (keyless, CORS open). Landsat (L30) is drawn below and
// Sentinel-2 (S30) above: empty tiles are transparent, so each fills the other's gaps.
export const HLS_LAYERS = ['HLS_L30_Nadir_BRDF_Adjusted_Reflectance', 'HLS_S30_Nadir_BRDF_Adjusted_Reflectance'] as const
export const HLS_MAXZOOM = 12 // GIBS native level; MapLibre overzooms past it
export const HLS_ATTRIBUTION = 'NASA GIBS · HLS'
export const hlsTiles = (layer: string, date: string) =>
  `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layer}/default/${date}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png`

export const HLS_DAYS = 8 // days stacked into the composite (2 sources per day)

// Shifts a YYYY-MM-DD date by n days (UTC).
export const shiftDate = (date: string, n: number) =>
  new Date(Date.parse(date + 'T00:00:00Z') + n * 86400000).toISOString().slice(0, 10)

// Days of the composite ending at `end`, oldest first (so newer days are drawn on top).
export const hlsWindow = (end: string) =>
  Array.from({ length: HLS_DAYS }, (_, i) => shiftDate(end, i - HLS_DAYS + 1))

// Fallback when GIBS cannot be asked: ten days ago (UTC), past the usual processing lag.
export function defaultHlsDate(): string {
  return shiftDate(new Date().toISOString().slice(0, 10), -10)
}

// Latest day GIBS serves for both HLS layers. Uses WMTS DescribeDomains (a few hundred bytes)
// instead of the ~6 MB GetCapabilities document. Resolves to null on any failure.
export async function fetchHlsLatest(): Promise<string | null> {
  const today = new Date().toISOString().slice(0, 10)
  const range = `${shiftDate(today, -120)}/${today}`
  try {
    const ends = await Promise.all(
      HLS_LAYERS.map(async (layer) => {
        const url =
          'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi?SERVICE=WMTS&REQUEST=DescribeDomains' +
          `&VERSION=1.0.0&LAYER=${layer}&TILEMATRIXSET=GoogleMapsCompatible_Level12&TIME=${range}`
        const text = await (await fetch(url)).text()
        const dates = text.match(/\d{4}-\d{2}-\d{2}/g)
        if (!dates) throw new Error('no dates')
        return dates.sort().at(-1)!
      }),
    )
    return ends.sort()[0] // the earlier of the two, so both layers have data
  } catch {
    return null
  }
}
