# Arquitectura propuesta para la base de entrenamiento NISAR–OPERA

**Estado:** propuesta para revisión del equipo. No describe una base completa ya generada.

## Objetivo

Construir una colección reproducible de recortes geográficos que relacione observaciones NISAR GCOV con etiquetas OPERA DIST-ALERT-HLS. La primera tarea prevista es detectar perturbación vegetal observada por OPERA y comparar su fecha con la adquisición NISAR. OPERA no identifica por sí solo la causa de la perturbación.

La base debe conservar las capas originales y su procedencia. Las etiquetas de entrenamiento se derivan con reglas versionadas. Así podremos cambiar filtros, polarizaciones y ventanas temporales sin perder la información fuente.

## Estructura de archivos propuesta

```text
data/datasets/<dataset_version>/
  dataset.json                    # versión, objetivo, grilla y reglas
  manifest.jsonl                  # una fila por recorte; índice simple inicial
  splits.jsonl                    # asignación por región/evento: train/valid/test
  samples/<sample_id>/
    features_frequencyA.tif       # canales A disponibles, misma grilla A
    features_frequencyB.tif       # opcional; conserva grilla B independiente
    labels_status.tif             # VEG-DIST-STATUS original
    labels_event_day.tif          # VEG-DIST-DATE original
    labels_event_delta_days.tif   # fecha de anomalía menos fecha NISAR
    labels_target.tif             # clase derivada, según regla versionada
    masks.tif                     # validez por canal, etiqueta y objetivo
    sample.json                   # fuentes, tiempos, grillas y procesamiento
  source_cache/<product_id>/      # fuentes compartidas, deduplicadas por granule
```

Cada GeoTIFF debe guardar CRS, transformación, resolución, `nodata`, nombres y unidades de bandas. `sample.json` registra valores de origen y parámetros de alineación. El manifiesto permite encontrar y combinar muestras sin abrir todos los rásteres. Si el índice crece, podrá materializarse también como Parquet.

Las fuentes completas no se copiarán dentro de cada muestra. El caché compartido evita descargar y almacenar varias veces el mismo TIFF OPERA. NISAR debe solicitarse por variable y área mediante Harmony; no hace falta bajar el HDF5 completo para crear un recorte.

## Variables

### Entradas NISAR

- **Frecuencia A:** `HHHH` y `HVHV` ya probadas. Añadir otros términos solo cuando el granule los contenga.
- **Frecuencia B:** guardar `HHHH` y `HVHV` si están disponibles, en archivo y grilla propios. El inventario del granule piloto lista ambos, pero aún no se extrajeron.
- **Calidad:** conservar `mask` y `numberOfLooks` por frecuencia; pueden servir para excluir o ponderar píxeles.
- **Representación:** GCOV entrega potencia gamma-0 calibrada y corregida por terreno, no amplitud compleja cruda. Guardar valores lineales; derivar dB durante el preprocesamiento si el modelo lo requiere.

`HHHH` es potencia del canal HH; `HVHV`, del canal HV. No son imágenes RGB. Los términos fuera de la diagonal, como `HHHV`, son complejos y contienen relaciones de amplitud y fase; quedan fuera del primer modelo.

**Frecuencia A/B no significa L-band/S-band.** Son frecuencias de adquisición dentro del producto del instrumento. En rutas `LSAR`, ambas pertenecen al instrumento L-band. El píxel de frecuencia B suele ser más grueso; verificar la grilla de cada granule. No remuestrear B a 30 m y tratarlo como detalle real. La utilidad de B se medirá comparando modelos A y A+B.

### Etiquetas OPERA

- `VEG-DIST-STATUS`: conservar códigos originales. En DIST-ALERT, `0` indica sin perturbación; `1–2` y `4–5` son estados iniciales/provisionales; `3`, `6`, `7` y `8` son confirmados; `255` es `nodata`.
- `VEG-DIST-DATE`: día de primera detección, contado desde 2020-12-31; precisión diaria.
- `event_delta_days`: fecha OPERA menos fecha de adquisición NISAR, por píxel. Valor negativo: detección anterior a NISAR. Positivo: posterior.
- `labels_target.tif`: clase de entrenamiento derivada; debe guardar la versión de la regla usada. No reemplaza los códigos originales.
- `masks.tif`: validez de cada canal, etiqueta fuente y píxel incluido en entrenamiento. Canales ausentes o sin cobertura nunca se rellenan como ceros válidos.

Una etiqueta con desfase positivo no representa un cambio que NISAR ya hubiera observado. Una fecha en el mismo día no permite ordenar eventos con precisión. La ventana temporal final y el tratamiento de estados provisionales siguen pendientes; la auditoría actual usa una sola zona y cinco píxeles negativos, insuficientes para fijarlos.

Si se desea clasificar causas —incendio, tala, deslizamiento u otra— se incorporará una etiqueta externa con fuente, fecha, confianza y regla espacial. No se inferirá causa desde `VEG-DIST-STATUS`.

## Metadatos por muestra

`sample.json` y `manifest.jsonl` deben incluir, como mínimo:

- IDs de granule, colección y producto NISAR/OPERA; URLs o referencias de fuente y checksums.
- Hora UTC de adquisición NISAR, tiempo de observación/actualización OPERA y desfase entre granules.
- Desfase de detección por píxel; no confundirlo con el desfase entre horas de escena.
- Canales realmente presentes, frecuencia, polarización, unidad, resolución de origen y método de remuestreo.
- CRS, transformación, dimensiones, resolución destino, huella, AOI y región/evento asociado.
- Versión de extractor, esquema, política temporal, codificación de clases y máscara de entrenamiento.
- Grupo de partición train/valid/test.

La partición debe hacerse por región, evento o bloque espacial antes de crear chips vecinos. No dividir píxeles aleatoriamente: eso filtraría zonas casi idénticas entre entrenamiento y evaluación.

## Tamaño orientativo

El piloto actual mide 39 × 32 píxeles. Sus cinco rásteres alineados ocupan cerca de 16 KB. La carpeta completa ocupa alrededor de 3,46 MB porque incluye TIFF OPERA fuente completos, recortes NISAR y metadatos.

Como referencia sin compresión, un chip de 128 × 128 con cuatro canales `float32` más estado, fecha, desfase y máscara ocupa cerca de 0,34 MiB. Diez mil chips ocuparían unos 3,4 GiB. Para 256 × 256, serían unos 1,38 MiB por chip y 13,4 GiB por diez mil. Con solo dos canales, las estimaciones bajan a 2,1 y 8,5 GiB por diez mil, respectivamente.

Estas cifras no incluyen caché de fuentes, bandas auxiliares, más fechas ni frecuencia B. La compresión GeoTIFF puede reducir el tamaño; medirla con varias regiones antes de fijar presupuesto. El tamaño total depende del número de granules únicos y de cuánto se reutilice el caché.

## Estado comprobado y trabajo pendiente

El piloto contiene una muestra de 39 × 32 píxeles, dos bandas de frecuencia A (`HHHH`, `HVHV`) promediadas a la grilla OPERA de 30 m, estado OPERA, fecha de primera detección, desfase diario y máscaras. No es todavía una base de entrenamiento completa. La carpeta piloto mantiene fuentes por muestra; el caché compartido descrito arriba es una mejora pendiente.

Antes de generar la base amplia faltan: repetir auditoría temporal en varias zonas positivas y de fondo; fijar política de etiquetas y muestreo; decidir tratamiento de frecuencia B; acordar tamaño de chip y grilla; y crear particiones espaciales. Este documento propone estructura, no ejecuta esas etapas.

## Referencias de producto

- [Guía de usuario NISAR GCOV](https://nisar-docs.asf.alaska.edu/gcov/)
- [Guía de formato HDF5 NISAR](https://nisar-docs.asf.alaska.edu/data-format/)
- [Guía de frecuencias y canales NISAR](https://nisar-docs.asf.alaska.edu/nisar-intro/)
- [Especificación OPERA DIST-HLS v1](https://d2pn8kiwq2w21t.cloudfront.net/documents/OPERA_DIST_HLS_Product_Specification_V1.pdf)
