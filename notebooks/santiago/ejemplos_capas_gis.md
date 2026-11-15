# Ejemplos concretos para las capas GIS de contexto

Complementa `informe_capas_gis.md` (§2 y §4). Fecha de consulta: 2026-11-15.

Verificación:
- Los IDs y rangos de fecha de GIBS salen de `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml`, descargado ese día.
- "200" significa que se pidió la tesela z5/x9/y12 o el recurso con `curl` y respondió HTTP 200.
- Los bbox van en `[oeste, sur, este, norte]` (WGS84). Son aproximados y están hechos a mano alrededor del evento.

## Plantilla común de GIBS (EPSG:3857)

```
https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{LAYER}/default/{YYYY-MM-DD}/{TileMatrixSet}/{z}/{y}/{x}.png
```

| Capa GIBS (ID verificado) | TileMatrixSet | Rango de fechas (GetCapabilities) | Valor por defecto |
|---|---|---|---|
| `NISAR_L2_Geocoded_Polarimetric_Covariance` | `GoogleMapsCompatible_Level13` | 2026-08-10 → 2026-11-13, P1D | 2026-11-13 |
| `OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1` | `GoogleMapsCompatible_Level12` | 2025-10-24 → 2026-11-15, P1D | 2026-11-15 |
| `OPERA_L3_Dynamic_Surface_Water_Extent-HLS` | `GoogleMapsCompatible_Level12` | 2025-08-08 → 2026-11-05, P1D | 2026-11-05 |
| `OPERA_L3_DIST-ANN-HLS_Color_Index` | `GoogleMapsCompatible_Level12` | 2023-01-01 → 2025-01-01, P1Y | 2025-01-01 |
| `OPERA_L3_DIST-ALERT-HLS_Color_Index` | `GoogleMapsCompatible_Level12` | 2026-02-10 → 2026-11-05, P1D | 2026-11-05 |
| `HLS_S30_Nadir_BRDF_Adjusted_Reflectance` | `GoogleMapsCompatible_Level12` | 2026-03-02 → 2026-11-07, P1D | 2026-11-07 |
| `HLS_L30_Nadir_BRDF_Adjusted_Reflectance` | `GoogleMapsCompatible_Level12` | existe en GetCapabilities (rango no revisado) | — |

Notas:
- La ventana de NISAR GCOV en GIBS empieza el **2026-08-10**. Los ejemplos con overlay NISAR deben ser de esa fecha en adelante.
- La ventana diaria de DSWx-S1 empieza el 2025-10-24. Antes de esa fecha, la tesela sale vacía.
- Teselas con 200 verificado: NISAR (2026-10-01), DSWx-S1 (2026-10-01) y DIST-ANN (2025-01-01). Que respondan 200 no garantiza que haya píxeles en esa zona. La cobertura es por pasada.

## Tabla de capas y ejemplos

| Capa | URL plantilla | Ejemplo (lugar, fecha, bbox) | Por qué sirve con NISAR | Fuente |
|---|---|---|---|---|
| NISAR GCOV (GIBS) | `.../NISAR_L2_Geocoded_Polarimetric_Covariance/default/{fecha}/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png` (200) | Terremoto M7.7 en Panamá (Azuero), 2026-10-09. Comparar antes y después: 2026-09 frente a 2026-10/11. bbox `[-81.3, 7.2, -80.2, 8.1]` | Vista rápida del retrodispersado L-band sin backend. Sirve para elegir fechas antes de bajar el GCOV completo. | [GIBS GetCapabilities](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml), [USGS evento](https://earthquake.usgs.gov/fdsnws/event/1/query?format=csv&starttime=2026-08-10&endtime=2026-11-15&minmagnitude=7) |
| OPERA DSWx-S1 | `.../OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1/default/{fecha}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png` (200) | Inundación del Parque Kruger y el Limpopo (Sudáfrica/Mozambique), 2026-01-12. bbox `[30.9, -25.5, 33.0, -22.3]`. NISAR publicó un mapa de inundación de este evento. | Agua de banda C (S1) frente a banda L (NISAR). La banda L detecta inundación bajo el dosel, porque HH sube por el doble rebote. | [GIBS](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml), [Earthdata NISAR L-band release](https://www.earthdata.nasa.gov/news/nisar-l-band-data-released-expanding-record-surface-changes) |
| OPERA DSWx-HLS | `.../OPERA_L3_Dynamic_Surface_Water_Extent-HLS/default/{fecha}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png` | Mismo caso del Kruger: el óptico de enero sale con nubes, y eso muestra la ventaja del radar. bbox igual. | Valida el agua abierta en días despejados. Contrasta con el SAR, que funciona con nubes. | [GIBS](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml) |
| OPERA DIST-ANN | `.../OPERA_L3_DIST-ANN-HLS_Color_Index/default/{2023-01-01\|2024-01-01\|2025-01-01}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png` (200) | Arco de deforestación de Rondônia (Brasil), año 2024. bbox `[-64.5, -11.0, -61.5, -8.5]`. Sin verificar visualmente. | La pérdida de bosque reduce HV, la retrodispersión de volumen. DIST-ANN da la verdad óptica anual. | [GIBS](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml) |
| OPERA DIST-ALERT | `.../OPERA_L3_DIST-ALERT-HLS_Color_Index/default/{fecha}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png` | Cualquier fuego o tala entre 2026-08 y 2026-11 que se solape con NISAR. No se buscó un evento concreto (sin verificar). | Es una alerta casi diaria. Permite cruzar fechas con los pasos de NISAR (12 días). | [GIBS](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml) |
| HLS S30/L30 | `.../HLS_S30_Nadir_BRDF_Adjusted_Reflectance/default/{fecha}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png` | Terremoto M7.8 en Flores (Indonesia), 2026-08-14. Deslizamientos visibles en el óptico. bbox `[120.8, -8.9, 121.9, -8.0]`. Hay fechas vacías; buscar la más cercana. | Color real de la misma fecha para interpretar el SAR. | [GIBS](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml), [USGS](https://earthquake.usgs.gov/fdsnws/event/1/) |
| JRC Global Surface Water | `https://storage.googleapis.com/global-surface-water/tiles2021/occurrence/{z}/{x}/{y}.png` (200) | Llanura del Limpopo / Kruger (bbox del caso DSWx). Agua histórica 1984–2021. | Separa el agua permanente de la inundación nueva en el GCOV. | [JRC GSW](https://global-surface-water.appspot.com/download) |
| Hansen GFC | `https://storage.googleapis.com/earthenginepartners-hansen/tiles/gfc_v1.12/loss_alpha/{z}/{x}/{y}.png` (200). Versión v1.12 = pérdida hasta 2024. | Rondônia, bbox del caso DIST-ANN. | Pérdida histórica de bosque como base. Explica el HV bajo en NISAR. | [Global Forest Watch / UMD](https://glad.earthengine.app/view/global-forest-change) |
| Esri World Imagery | `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}` (200) | Panamá (Azuero), bbox del caso NISAR. | Fondo de alta resolución para ubicar daños. Ojo: no tiene fecha controlable. | [Esri](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9) |
| Esri World Hillshade | `https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}` (200) | Terremoto M7.0 cerca de Nagqu (Tíbet), 2026-10-22. bbox `[93.0, 31.8, 94.6, 32.9]`. | El relieve explica las sombras y el layover del SAR en montaña. | [Esri](https://www.arcgis.com/home/item.html?id=1b243539f4514b6ba35e7d995890db1d) |
| AWS Terrarium (Mapzen) | `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png` (200). Altura = `R*256 + G + B/256 - 32768`. | Nagqu (Tíbet), mismo bbox. Terreno 3D en MapLibre. | Relieve 3D bajo el GCOV. Ayuda a interpretar la pendiente y la geometría de la iluminación del radar. | [AWS Open Data](https://registry.opendata.aws/terrain-tiles/) |
| USGS fdsnws | `https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime={a}&endtime={b}&minmagnitude={m}&minlatitude=..&maxlatitude=..&minlongitude=..&maxlongitude=..` (200) | Sismos M≥7 en la ventana de NISAR: Colombia M7.4 (2026-08-10), Flores M7.8 (2026-08-14), Panamá M7.7 (2026-10-09), Tíbet M7.0 (2026-10-22). | Pone los epicentros sobre el cambio en el SAR. Como referencia previa, Kamchatka M8.8 (2025-07-30) sigue disponible (200). | [USGS FDSN](https://earthquake.usgs.gov/fdsnws/event/1/) |

## Casos NISAR ya publicados (prioritarios)

| Caso | Fecha | bbox aprox. | Capas a combinar | Fuente |
|---|---|---|---|---|
| Inundación Kruger / Limpopo | 2026-01-12 | `[30.9, -25.5, 33.0, -22.3]` | DSWx-S1, DSWx-HLS, JRC GSW | [Earthdata](https://www.earthdata.nasa.gov/news/nisar-l-band-data-released-expanding-record-surface-changes) |
| Subsidencia de Ciudad de México (>2 cm/mes) | finales de 2025 a inicios de 2026 | `[-99.30, 19.20, -98.90, 19.60]` | Hillshade, Esri Imagery, OPERA DISP-S1 | [developmentstoday](https://developmentstoday.com/space/nisar-maps-mexico-city-subsidence-early-mission-test) |
| Pacific Northwest a través de nubes | 2025–2026 | `[-124.5, 45.5, -121.5, 48.5]` (sin verificar) | HLS, Hillshade | [JPL](https://www.jpl.nasa.gov/news/nasa-isro-satellite-captures-pacific-northwest-through-clouds/) |
| Glaciares de Antártida Oriental (banda S, ISRO) | 2026-07 | sin verificar | Terrarium | [ISRO](https://www.isro.gov.in/ISRO_EN/NISARS_Band_SAR_Data_Products_Release.html) |

## Capas nuevas sugeridas (gratis, sin clave)

| Capa | URL plantilla | Uso con NISAR | Estado | Fuente |
|---|---|---|---|---|
| OPERA RTC-S1 (GIBS) | `.../OPERA_L2_Radiometric_Terrain_Corrected_SAR_Sentinel-1/default/{fecha}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png`, rango 2026-01-05 → hoy | Comparación directa de banda C con banda L: mismo tipo de producto (retrodispersión corregida por terreno). Es la mejor capa para hablar de polarización y longitud de onda. | ID verificado | [GIBS](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml) |
| VIIRS anomalías térmicas (FIRMS en GIBS) | `.../VIIRS_NOAA20_Thermal_Anomalies_375m_All/default/{fecha}/{TMS}/{z}/{y}/{x}.png` (también SNPP y NOAA21) | Puntos de fuego activos para validar quemas en el GCOV. El informe vio 404 en MVT; probar la versión PNG. | ID verificado, tesela sin verificar | [GIBS](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml) |
| VIIRS/MODIS Combined Flood 1/2/3-Day (GIBS) | `.../VIIRS_Combined_Flood_2-Day/default/{fecha}/...` | Inundación óptica diaria (LANCE). Complementa DSWx. | ID verificado | [GIBS](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml) |
| Copernicus DEM GLO-30 (COG en AWS) | `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{N07_00}_{W081_00}_DEM/Copernicus_DSM_COG_10_{N07_00}_{W081_00}_DEM.tif` (200) | DEM de 30 m. Es la misma base de terreno que usan los productos NISAR y OPERA. Se sirve con `rio-tiler`. | 200 | [AWS Open Data](https://registry.opendata.aws/copernicus-dem/) |
| ESA WorldCover 10 m (COG en AWS) | `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{N06W081}_Map.tif` (200) | Clases de cobertura del suelo para interpretar la polarimetría (bosque, cultivo, urbano). | 200 | [AWS Open Data](https://registry.opendata.aws/esa-worldcover-vito/) |
| OPERA DISP-S1 | Sin teselas XYZ públicas. Se descarga con ASF/earthaccess (NetCDF). Requiere login de Earthdata, que es gratis. | Deformación InSAR de banda C para comparar con la subsidencia que mide NISAR (p. ej. CDMX). | Sin verificar (requiere login) | [ASF OPERA](https://asf.alaska.edu/datasets/daac/opera/) |
| Global Flood Database (Cloud to Street / GEE) | Solo GEE (`GLOBAL_FLOOD_DB/MODIS_EVENTS/V1`). No hay XYZ directo. | Inundaciones históricas 2000–2018 como contexto. | Sin verificar, poco práctico | [GEE catalog](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1) |
| Órbitas NISAR (GIBS) | `OrbitTracks_NISAR_Ascending` / `_Descending` | Muestra qué pasadas cubren el área de estudio. El informe vio 400 en MVT; probar la versión PNG. | ID verificado | [GIBS](https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml) |
