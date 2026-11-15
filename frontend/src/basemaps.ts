import type { StyleSpecification } from 'maplibre-gl'

export type BasemapId = 'gray' | 'osm'

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
}

export const BASEMAP_IDS: BasemapId[] = ['gray', 'osm']
