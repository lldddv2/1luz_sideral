import type { FeatureCollection, Point } from 'geojson'

// Mock points of interest (frontend-only). Coordinates are [lng, lat].
// Illustrative values, not NISAR results. change_db = simple mean of HH and HV.

export type PoiCategory = 'wildfire' | 'flood' | 'subsidence' | 'glacier' | 'crop' | 'quake'
export type PoiPol = 'HH' | 'HV' | 'VH' | 'VV'

export interface PoiProps {
  id: string
  name: string
  category: PoiCategory
  date: string // YYYY-MM-DD
  change_db: number
  pol: Partial<Record<PoiPol, number>>
  hypothesis: string
  source: string
}

export const POI_COLOR: Record<PoiCategory, string> = {
  wildfire: '#dc2626',
  flood: '#1d4ed8',
  subsidence: '#92400e',
  glacier: '#22d3ee',
  crop: '#65a30d',
  quake: '#db2777',
}

export const POI_LABEL: Record<PoiCategory, string> = {
  wildfire: 'Incendio',
  flood: 'Inundación',
  subsidence: 'Hundimiento',
  glacier: 'Glaciar',
  crop: 'Cultivo',
  quake: 'Sismo',
}

export const POIS: FeatureCollection<Point, PoiProps> = {
  type: 'FeatureCollection',
  features: [
    { type: 'Feature', geometry: { type: 'Point', coordinates: [-105.01, 39.98] }, properties: { id: 'b01', name: 'Campo de riego (demo)', category: 'crop', date: '2026-10-30', change_db: 2.3, pol: { HH: 1.2, HV: 3.4 }, hypothesis: 'Crecimiento de biomasa: HV sube más que HH (dispersión de volumen).', source: 'mock' } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [-104.97, 40.025] }, properties: { id: 'b02', name: 'Cauce inundado (demo)', category: 'flood', date: '2026-09-12', change_db: -6.6, pol: { HH: -7.4, HV: -5.8 }, hypothesis: 'Agua en superficie especular: retrodispersión baja en ambas polarizaciones.', source: 'mock' } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [-105.035, 40.03] }, properties: { id: 'b03', name: 'Pastizal quemado (demo)', category: 'wildfire', date: '2026-08-19', change_db: -4.0, pol: { HH: -3.0, HV: -5.0 }, hypothesis: 'Pérdida de dosel por fuego: HV cae más que HH (volumen dispersor perdido).', source: 'mock' } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [-104.995, 39.965] }, properties: { id: 'b04', name: 'Zona de hundimiento (demo)', category: 'subsidence', date: '2026-10-30', change_db: -0.3, pol: { HH: -0.4, HV: -0.2 }, hypothesis: 'Subsidencia: la señal principal está en fase (InSAR); la amplitud cambia poco.', source: 'mock' } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [-105.025, 39.99] }, properties: { id: 'b05', name: 'Daño sísmico (demo)', category: 'quake', date: '2026-10-06', change_db: -3.6, pol: { HH: -4.2, HV: -3.0 }, hypothesis: 'Daño o deslizamiento: cambia rugosidad y doble rebote (no validada).', source: 'mock' } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [-75.34, 4.895] }, properties: { id: 'r01', name: 'Glaciar en retroceso (demo)', category: 'glacier', date: '2026-09-24', change_db: -3.2, pol: { HH: -3.8, HV: -2.6 }, hypothesis: 'Nieve húmeda o fusión superficial: reduce la retrodispersión en ambas polarizaciones.', source: 'mock' } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [-75.305, 4.87] }, properties: { id: 'r02', name: 'Quema de páramo (demo)', category: 'wildfire', date: '2026-08-31', change_db: -3.5, pol: { HH: -2.6, HV: -4.4 }, hypothesis: 'Pérdida de cobertura de páramo: HV cae más que HH.', source: 'mock' } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [-75.36, 4.925] }, properties: { id: 'r03', name: 'Deslizamiento (demo)', category: 'quake', date: '2026-10-18', change_db: -4.3, pol: { HH: -5.0, HV: -3.6 }, hypothesis: 'Deslizamiento: cambia la geometría dispersora y el doble rebote (no validada).', source: 'mock' } },
    { type: 'Feature', geometry: { type: 'Point', coordinates: [-75.29, 4.86] }, properties: { id: 'r04', name: 'Ladera con cultivo (demo)', category: 'crop', date: '2026-10-06', change_db: 1.9, pol: { HH: 0.8, HV: 3.0 }, hypothesis: 'Crecimiento del cultivo: HV sube más que HH.', source: 'mock' } },
  ],
}
