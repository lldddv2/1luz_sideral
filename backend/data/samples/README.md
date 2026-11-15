# Imágenes de muestra

Carpeta para GeoTIFF de prueba (`.tif` / `.tiff`). El backend la escanea y expone cada archivo en `/api/samples` con su ubicación (CRS, bounds en EPSG:4326) y su fecha, para mostrarlo en el mapa y en la línea de tiempo.

## Cómo agregar una imagen

- Copiar el archivo aquí, o subirlo con `POST /api/samples` (multipart, campo `file`, opcional `datetime` y `label`; máximo 200 MB).
- El archivo debe ser un GeoTIFF con CRS.
- Los `.tif` no se versionan en git (están en `.gitignore`); solo este README, `.gitkeep` y los `.json`.

## Nombre

- El `id` es el nombre sin extensión convertido a slug (minúsculas; caracteres raros se vuelven `-`). Ej.: `S1 VV 2024.tif` → `s1-vv-2024`.
- Conviene incluir la fecha en el nombre: `NISAR_20251103_HH.tif` o `zona_2025-11-03.tif`.

## De dónde sale la fecha (en este orden)

1. Archivo lateral `<nombre>.json` junto al `.tif` (campo `datetime`).
2. Tags del TIFF: `TIFFTAG_DATETIME`, `ACQUISITION_DATE`, `DATE_TIME` u otro tag con fecha en cualquier namespace.
3. Fecha en el nombre: `YYYYMMDDTHHMMSS`, `YYYY-MM-DD` o `YYYYMMDD`.
4. Si no hay ninguna, `datetime` es `null` y `time_source` es `"none"`.

La respuesta indica siempre `time_source` (`sidecar`, `tag:...`, `filename`, `none`).

## Archivo lateral

```json
{
  "datetime": "2025-11-03T12:00:00Z",
  "label": "Texto para la interfaz",
  "sensor": "NISAR L-band",
  "polarization": "HH",
  "notes": "Comentario libre"
}
```

Solo `datetime` es relevante para la fecha; los demás campos son opcionales y se devuelven tal cual.
