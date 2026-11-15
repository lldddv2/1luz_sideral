# Informe: capas GIS e integración del raster NISAR en el mapa

Fecha: 2026-11-14 · Rama: `dev-santiago` · Solo simulación, sin cambios en `frontend/` ni `backend/`.

## Resumen

- **Raster NISAR:** imagen única. El backend la reproyecta a EPSG:3857, la codifica en WebP (calidad 80) y devuelve sus 4 esquinas. El front la muestra con una fuente `image` de MapLibre.
- **Contexto óptico:** Esri World Imagery como mapa base adicional.
- **Capas temáticas:** teselas o GeoJSON externos, sin pasar por el backend. Se eligen según el tipo de cambio, que aún no está decidido.

## 1. Raster NISAR: imagen única (A) vs teselas XYZ (B)

Datos: GeoTIFF GCOV HH reales de `bench_output/` (Boulder, CO; 10 m; EPSG:32613).
Script: `bench/bench_overlay.py`. Resultados: `bench_output/bench_overlay.json`.

- **A:** imagen única reproyectada a EPSG:3857, servida a una fuente `image`.
- **B:** COG + `rio-tiler` (como TiTiler), servido como fuente `raster` XYZ.

| Área | A: WebP q80 | A: PNG | A: tiempo servidor | B: vista inicial | B: con 3 niveles de zoom |
|---|---|---|---|---|---|
| 1.5 km | 9 KB | 30 KB | 13 ms | 38 KB (9 teselas) | 176 KB |
| 5 km | 95 KB | 314 KB | 58 ms | 271 KB | 1.2 MB |
| 10 km | 381 KB | 1.2 MB | 220 ms | 449 KB | 3.1 MB |
| 20 km | 1.5 MB | 4.9 MB | 880 ms | 474 KB | 6.6 MB |

"Tiempo servidor" incluye reproyección y codificación WebP. "Vista inicial" son las teselas que hay que pedir para mostrar el área entera la primera vez, en una ventana de ~1100×800 px.

**Slider temporal (6 fechas, 10 km):**

- A: 2.3 MB en total en WebP (7.4 MB en PNG). Se cargan todas las fechas una vez y cambiar de fecha es instantáneo.
- B: 2.7 MB solo para la vista inicial. Hay que volver a pedir teselas en cada fecha y cada zoom, y el mapa parpadea al cambiar.

**Error de no reproyectar:** pasar las esquinas UTM directamente a la fuente `image` deja un error máximo de 0.04 m (1.5 km), 1.65 m (10 km) y 6.6 m (20 km). Siempre es menos de 1 píxel, pero reproyectar cuesta solo ~150 ms, así que conviene hacerlo.

**Límite de A:** el límite de descarga es 2500 km², unos 50 km de lado. A 10 m eso son ~5000 px, por encima de la textura habitual de la GPU (4096 px). Para áreas de más de ~40 km hay que reducir la imagen a ≤4096 px (~12 m por píxel).

**Decisión: A.** Es más simple (un endpoint), mejor para el slider temporal y suficiente para áreas de hasta 2500 km². B solo compensa con áreas mucho mayores.

## 2. Capas GIS de contexto

Pruebas desde la red local con `Origin: http://localhost:5173`, en el área del bench, con 3 peticiones por capa.
Script: `bench/bench_layers.py`. Resultados: `bench_output/bench_layers.json`.

| Capa | Uso | Respuesta | CORS | Veredicto |
|---|---|---|---|---|
| Esri World Imagery | Óptico de referencia | 323 ms, 19 KB | `*` | Usar como mapa base |
| OPERA DSWx-S1 / DSWx-HLS (GIBS) | Validar agua, humedales e inundación | 520–590 ms | `*` | Usar si el cambio es agua |
| OPERA DIST-ANN (GIBS) | Validar fuego y deforestación | 2.8 KB; 3.8 s la primera vez | `*` | Usar si el cambio es fuego o bosque |
| JRC Global Surface Water | Agua histórica | 338 ms | `*` | Usar |
| Hansen GFC pérdida de bosque | Deforestación | 371 ms | `*` | Usar |
| Esri World Hillshade | Relieve | 310 ms, 7 KB | `*` | Usar (más ligera que el DEM) |
| AWS Terrarium DEM | Relieve con `hillshade` nativo de MapLibre | 652 ms, 102 KB | `*` | Alternativa más pesada |
| USGS sismos (fdsnws por bbox) | Deformación y subsidencia | 314 B | `*` | Usar la consulta por bbox, no el feed completo (7 MB, 9917 eventos) |
| HLS Sentinel-2 30 m (GIBS) | Óptico de la misma fecha | 4 de 5 fechas vacías | `*` | Buscar la fecha más cercana con datos |
| NISAR GCOV (GIBS) | Vista previa de NISAR sin backend | Cobertura inconsistente entre zooms y fechas, un error 500 | `*` | Solo vista previa, no para análisis |
| MODIS true color (GIBS) | Óptico diario | 4 s, 250 m | `*` | Descartada: demasiado gruesa |
| ESA WorldCover (Terrascope) | Cobertura del suelo | Sin conexión | — | Descartada |
| Incendios VIIRS y órbitas NISAR (GIBS, MVT) | Fuego, cobertura orbital | 404 / 400 | `*` | Descartada por ahora |

Ninguna capa requiere clave de API.

## 3. Integración propuesta

- **Orden de capas:** mapa base → contexto → NISAR → mapa de cambio (log-ratio) → áreas de estudio. Todo debajo de `aoi-region-fill`, usando `beforeId`.
- **Capas declarativas:** `<Source>`/`<Layer>` como hijos de `<Map>` en `MapView`, no dentro del estilo del mapa base. Así se mantienen al cambiar de mapa base.
- **Catálogo:** nuevo `frontend/src/layers.ts` con el mismo patrón que `basemaps.ts` (id, etiqueta, pista, URL de teselas, atribución).
- **Opacidad:** el slider de "Capas" guarda hoy su estado dentro de `Sidebar` y no llega al mapa. Hay que subirlo a `App`.
- **Backend:** nuevo endpoint que devuelva la WebP y las 4 esquinas en lon/lat. Requiere añadir `rasterio` y `pillow` al backend.

## 4. Capas según el tipo de cambio

| Tipo de cambio | Capas de contexto |
|---|---|
| Humedales / inundación | OPERA DSWx, JRC Surface Water, HLS |
| Fuego / deforestación | OPERA DIST, Hansen GFC, HLS |
| Sismo / subsidencia | USGS sismos, Hillshade |
| Glaciares | Hillshade, HLS |
| Agricultura | HLS, Esri World Imagery |

## Límites

- No se midió el renderizado en navegador (FPS, memoria de GPU).
- La latencia es de pocas peticiones desde una sola red. Algunos servicios de GIBS tardan ~4 s con la caché fría.
- Para reproducir `bench_overlay.py` hacen falta `rasterio`, `rio-tiler`, `rio-cogeo` y `pillow`. `bench_layers.py` solo necesita `requests`.
