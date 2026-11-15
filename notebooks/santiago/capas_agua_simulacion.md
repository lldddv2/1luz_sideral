# Simulación de capas GIS de agua

Fecha: 2026-11-15 · Script: `bench/bench_water_layers.py` · Resultados: `bench_output/bench_water_layers.json`.

Método: `requests` con `Origin: http://localhost:5173`. Por capa y área se piden 2–4 teselas dentro del bbox (centro y cuadrantes), con hasta 3 reintentos si se cae la conexión. "¿Píxeles?" = teselas con alguna fracción no transparente (PIL, canal alfa). Las fechas de GIBS se validan contra GetCapabilities.

Áreas:
- **Kruger / Limpopo** (inundación publicada por NISAR), 2026-01-12, bbox `[30.9, -25.5, 33.0, -22.3]`.
- **CDMX** (subsidencia por sobreexplotación del acuífero), 2026-10-01, bbox `[-99.30, 19.20, -98.90, 19.60]`.

## Resultados

| Capa | Área | Fecha | HTTP | Latencia (mediana) | ¿Píxeles? | CORS | Veredicto |
|---|---|---|---|---|---|---|---|
| NISAR GCOV (GIBS, z10) | Kruger | 2026-01-12 | 200 | 815 ms | 3/4 | `*` | Sirve |
| NISAR GCOV (GIBS, z10) | CDMX | 2026-10-01 | 200 | 827 ms | 3/3 | `*` | Sirve |
| OPERA DSWx-S1 (z10) | Kruger | 2026-01-12 | 200 (un 500 en la 1.ª corrida) | 556 ms | 2/4 | `*` | Sirve; cobertura por pasada |
| OPERA DSWx-S1 (z10) | CDMX | 2026-10-01 | 200 | 612 ms | 3/3 | `*` | Sirve |
| OPERA DSWx-HLS (z10) | Kruger | 2026-01-12 | 200 | 564 ms | 3/4 | `*` | Sirve (puede tener nubes) |
| OPERA DSWx-HLS (z10) | CDMX | 2026-10-01 | 200 | 625 ms | 2/3 | `*` | Sirve |
| OPERA RTC-S1 (z10) | Kruger | 2026-01-12 | 200 | 526 ms | 0/4 | `*` | Sin pasada ese día en Kruger |
| OPERA RTC-S1 (z10) | CDMX | 2026-10-01 | 200 | 795 ms | 3/3 | `*` | Sirve |
| VIIRS Combined Flood 3-Day (z8) | Kruger | 2026-01-12 | 200 | 649 ms | 4/4 | `*` | Sirve; 375 m, solo vista regional |
| VIIRS Combined Flood 3-Day (z8) | CDMX | 2026-10-01 | 200 | 748 ms | 2/2 | `*` | Sirve |
| MODIS Combined Flood 3-Day (z8) | Kruger | 2026-01-12 | 200 | 671 ms | 4/4 | `*` | Sirve; 250 m, redundante con VIIRS |
| MODIS Combined Flood 3-Day (z8) | CDMX | 2026-10-01 | 200 | 754 ms | 2/2 | `*` | Sirve |
| JRC GSW occurrence (z10) | Kruger | — (1984–2021) | 200 | 334 ms | 1/4 | `*` | Sirve; poca agua permanente en la llanura |
| JRC GSW occurrence (z10) | CDMX | — | 200 | 336 ms | 2/3 | `*` | Sirve |
| JRC GSW change (z10) | Kruger | — | 200 | 360 ms | 4/4 | `*` | Sirve |
| JRC GSW change (z10) | CDMX | — | 200 | 337 ms | 3/3 | `*` | Sirve |
| GLDAS humedad del suelo subterránea (mensual, z5) | Kruger | 2026-01 | 200 | 602 ms | 1/1 | `*` | Sirve; ~25 km, solo contexto |
| GLDAS (mensual, z5) | CDMX | 2026-06-01 (último mes) | 200 | 1758 ms | 1/1 | `*` | Sirve; desfase de meses |
| GRACE LWE mascon (GIBS) | ambas | fuera de rango (termina 2022-07) | 404 | 495 ms | 0 | `*` | Descartada: datos viejos |
| WHYMAP / IGRAC acuíferos | — | — | — | — | — | — | Sin verificar (no se halló tesela XYZ sin clave) |

Nota: la primera corrida dio `ConnectionError` en varias capas de GIBS. Con reintentos todo respondió. Hay que prever reintentos o tolerar teselas caídas en el front.

## Primeras capas a probar (orden)

1. **OPERA DSWx-S1**: agua de banda C con nubes o sin ellas, 30 m, mismas fechas que NISAR; la mejor comparación directa para inundación.
2. **NISAR GCOV (GIBS)**: vista previa de banda L sin backend; ya cubre Kruger (ene 2026) y CDMX (oct 2026).
3. **JRC GSW change / occurrence**: la más rápida (~340 ms), estática; separa agua permanente de inundación nueva.
4. **VIIRS Combined Flood 3-Day**: contexto regional diario de la inundación, pero grueso (375 m).
5. **OPERA DSWx-HLS**: validación óptica en días despejados.

Para CDMX (subsidencia) ninguna capa de teselas muestra el acuífero: hace falta OPERA DISP-S1 (login Earthdata) o el InSAR propio de NISAR. GLDAS solo da contexto hídrico grueso.

## Errores y correcciones en `ejemplos_capas_gis.md`

- **NISAR GCOV no empieza el 2026-08-10.** GetCapabilities tiene 5 rangos: 2025-10-29→2026-03-01, 2026-03-04→03-29, 2026-04-01→04-12, 2026-04-14→07-27 y 2026-08-10→11-13. El caso Kruger (2026-01-12) sí tiene overlay NISAR (verificado: 3/4 teselas con píxeles).
- **DSWx-S1 no empieza el 2025-10-24.** Hay 12 rangos desde 2023-12-15; 2025-10-24 es solo el inicio del último.
- **DSWx-HLS no empieza el 2025-08-08.** Hay rangos desde 2016-01-07; 2025-08-08 es solo el último.
- **Órbitas NISAR:** GetCapabilities solo ofrece MVT (`application/vnd.mapbox-vector-tile`), no hay versión PNG. La sugerencia de "probar PNG" no aplica.
- **VIIRS/MODIS Combined Flood:** el TileMatrixSet es `GoogleMapsCompatible_Level9` (z máx. 9); no figura en el ejemplo.
- **GRACE en GIBS** (`GRACE_Tellus_Liquid_Water_Equivalent_Thickness_Mascon_CRI`) termina en 2022-07; no sirve para la ventana NISAR.
- El resto de IDs, plantillas y bbox revisados coinciden con GetCapabilities y responden 200.
