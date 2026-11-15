# Sincronización exploratoria NISAR–OPERA

La arquitectura propuesta para la base final está documentada en
[`ARQUITECTURA_BASE_ENTRENAMIENTO.md`](ARQUITECTURA_BASE_ENTRENAMIENTO.md).
Es una propuesta; todavía no se genera la base amplia.

`catalog_sync.py` busca metadatos en NASA CMR y crea pares candidatos por
cercanía temporal y cobertura espacial. No descarga granules ni imágenes.

## Salida

Cada ejecución crea `catalog/<run_id_utc>/` con:

- `catalogs.json`: granules hallados en NISAR GCOV, OPERA DIST-ALERT y OPERA DSWx.
- `pairs.jsonl`: una fila JSON por par NISAR–OPERA dentro del umbral temporal.
- `summary.json`: consultas, conteos y límites del filtro espacial.
- `pair_audit.json`: huellas y metadatos del par DIST-ALERT más cercano.

Cada pareja conserva ambos tiempos UTC, desfase firmado en segundos con
precisión de milisegundos y horas con seis decimales, y desfase absoluto en
segundos y días. Positivo significa OPERA posterior a NISAR. La clase temporal
usa tiempos de inicio de granule; no indica momento causal del cambio.

La AOI predeterminada es un rectángulo pequeño y provisional en Central Valley,
California. Cámbiala en `config/central_valley_candidate.json` antes de decidir
zona final. Umbral temporal predeterminado: seis días.

## Ejecucion

Requiere Python 3 y `requests`. Instala dependencia con `pip install -r requirements.txt`.

```bash
python catalog_sync.py --start 2026-10-21 --stop 2026-11-14
```

Para ampliar ventana o tolerancia:

```bash
python catalog_sync.py --start 2026-10-21 --stop 2026-11-14 --tolerance-days 3
```

El catálogo filtra NISAR GCOV de configuración PR. La búsqueda consulta solo
CMR. No usa credenciales Earthdata ni abre enlaces de datos.

El filtro espacial usa el filtro AOI de CMR y solape de envolventes de huellas.
No confirma intersección exacta de polígonos ni alineamiento de píxeles. Eso
corresponde a una etapa posterior, tras seleccionar pares.

La auditoría del mejor par comprueba las cuatro esquinas de AOI contra los
polígonos UMM de ambos productos y registra CRS, polarizaciones y capas. Aún
no alinea rásteres.

## Muestra pequeña

`extract_sample.py` descarga solo `VEG-DIST-STATUS` y revisa salida NISAR
`frequencyA/HHHH` ya extraída por Harmony. Limita descarga OPERA a 8 MiB y
guarda datos bajo `data/`, excluido de Git. Requiere entorno instalado desde
`requirements-extraction.txt`, credenciales Earthdata en `.netrc` y el
extractor local `notebooks/jose/nisar_extractor` para obtener NISAR primero.

```bash
PYTHONPATH=../jose .venv/bin/python extract_sample.py
```

La prueba descargó TIFF OPERA de 1.136.061 bytes y generó recorte de 32×39
píxeles; recorte NISAR mide 92×112. Ambos usan EPSG:32611. OPERA tiene píxel
de 30 m; NISAR, 10 m. Grillas anidadas: pixel OPERA equivale a 3×3 píxeles
NISAR y ambos orígenes caen en retícula de 10 m. Aún no se remuestrean.

Los 1.248 píxeles válidos del recorte OPERA tienen clase `0` (`no_disturbance`).
Esta AOI pequeña sirve para revisar formato, no para entrenar ni mostrar un
cambio positivo. Par elegido: NISAR 2026-10-26 13:08:57 UTC; OPERA
2026-10-27 18:54:18.187 UTC; desfase +107.121,187 s (+29,755885 h). Metadata
del TIFF cita granule de entrada del 23 de octubre; la capa recibió
actualización el 27. Ver detalle en
[`sample_alignment.json`](catalog/20261114T231448Z/sample_alignment.json).

## Ventanas con etiqueta positiva

`find_positive_aoi.py` recorre el TIFF OPERA ya descargado y conserva ventanas
con cobertura completa dentro de la huella NISAR. No descarga datos nuevos.
Usa ventanas de 32×39 píxeles, como la primera muestra.

Mejor candidata: `[-120.2412837, 36.2694577, -120.2301769, 36.2802780]`.
Contiene 1.243 píxeles positivos; 1.240 son confirmados: 1.156 clase 3
(pérdida vegetal confirmada <50%) y 84 clase 6 (confirmada ≥50%). La huella
NISAR cubre el 100% de ventana. Otras cuatro opciones constan en
[`candidate_positive_aois.json`](catalog/20261114T231448Z/candidate_positive_aois.json).

Estas clases describen pérdida vegetal; no identifican su causa. La primera
fecha de anomalía consta en `VEG-DIST-DATE`.

## Sincronización piloto de entrenamiento

`sync_training_pilot.py` crea una muestra pequeña desde la ventana positiva con
mejor puntuación. Confirma el granule NISAR por CMR, extrae solo las variables
seleccionadas con Harmony y descarga dos TIFF OPERA con límite de 8 MiB cada
uno. La salida NISAR tiene límite de 32 MiB; no descarga el HDF5 completo.

Por defecto usa `frequencyA/HHHH` y `frequencyA/HVHV`. Se pueden pedir más
canales con `--nisar-variable` repetido. Ejemplo:

```bash
PYTHONPATH=../jose .venv/bin/python sync_training_pilot.py \
  --nisar-variable /science/LSAR/GCOV/grids/frequencyA/HHHH \
  --nisar-variable /science/LSAR/GCOV/grids/frequencyA/HVHV
```

Cada muestra queda en `data/datasets/<catalog_run>/samples/<sample_id>/`:

- `sources/`: TIFF de fuente y recortes NISAR/OPERA para trazabilidad.
- `aligned/features_frequencyA.tif`: bandas NISAR HH y HV, float32.
- `aligned/labels_status.tif`: clases originales de OPERA.
- `aligned/labels_event_day.tif`: fecha OPERA original, días desde 2020-12-31.
- `aligned/labels_event_delta_days_from_nisar.tif`: desfase diario por píxel.
- `aligned/valid_sample_mask.tif`: píxeles con características y clase válidas.
- `sample.json`: canales, fuentes, grilla, tiempos, desfases y estadísticas.
- `manifest.jsonl`: índice combinable de muestras.

NISAR nativo tiene píxel de 10 × 10 m. Esta muestra agrega su potencia gamma0
lineal a la grilla OPERA de 30 × 30 m, con promedio de área. Rásteres alineados
comparten EPSG:32611, transformación y dimensiones; no se interpola fecha o
clase categórica.

La primera muestra mide 39 × 32 píxeles: 1.243 píxeles con perturbación, 1.240
confirmados y cobertura válida completa. El evento varía entre −108 y +1 días
respecto de NISAR; dos píxeles tienen fecha de anomalía posterior por un día.
La diferencia entre tiempos de adquisición es +107.121,187 s, pero no representa
el inicio del evento. `VEG-DIST-DATE` marca el primer día de detección, contado
desde 2020-12-31, según la [especificación OPERA DIST](https://d2pn8kiwq2w21t.cloudfront.net/documents/OPERA_DIST_HLS_Product_Specification_V1.pdf).

La descarga ocupa 3,46 MB en total; los recortes NISAR suman menos de 100 KB.
Es una prueba del flujo y del esquema, no una base suficiente para entrenar.
Antes de ampliar descargas, auditaremos filtros temporales y clases válidas.

### Auditoría de ventanas temporales

`audit_temporal_windows.py` compara ventanas retrospectivas sobre TIFF ya
alineados; no descarga datos. Conserva etiquetas positivas cuya primera fecha
de anomalía OPERA cae entre `N` y un día antes de NISAR (`[-N, -1]`). Excluye
fechas posteriores, porque el cambio aún no estaba observado por NISAR. Una
fecha en el mismo día también se excluye: la fecha OPERA solo tiene precisión
diaria y no permite ordenar observación frente a adquisición.

```bash
.venv/bin/python audit_temporal_windows.py
```

La auditoría actual usa una sola ventana positiva de 39 × 32 píxeles:

| Ventana anterior a NISAR | Positivos retenidos | Confirmados | De 1.243 positivos |
| ---: | ---: | ---: | ---: |
| 7 días | 0 | 0 | 0 % |
| 14 días | 0 | 0 | 0 % |
| 30 días | 7 | 6 | 0,56 % |
| 45 días | 333 | 332 | 26,79 % |
| 60 días | 705 | 704 | 56,72 % |
| 90 días | 1.106 | 1.105 | 88,98 % |
| 120 días | 1.241 | 1.240 | 99,84 % |

Dos positivos tienen fecha posterior a NISAR y quedan fuera. La ventana tiene
solo cinco píxeles sin perturbación; no permite evaluar balance ni definir un
umbral final. El reporte reproducible está en
[`temporal_filter_audit.json`](catalog/20261114T231448Z/temporal_filter_audit.json).
Se requiere repetir el análisis en varias zonas positivas y de fondo antes de
fijar una ventana para la base de entrenamiento.

## Alcance de las etiquetas OPERA

`VEG-DIST-STATUS` etiqueta estado, confianza y magnitud de pérdida vegetal.
No identifica causa como incendio, deslizamiento, tala o sequía. Para entrenar
una clase causal, habrá que cruzar OPERA con inventarios independientes de
eventos y conservar esa etiqueta externa como fuente distinta.

Referencias: [especificación DIST v1 de JPL](https://d2pn8kiwq2w21t.cloudfront.net/documents/OPERA_DIST_HLS_Product_Specification_V1.pdf)
y [página oficial OPERA DIST](https://www.jpl.nasa.gov/go/opera/products/dist-product-suite/).
