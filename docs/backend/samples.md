# Samples

Code: `backend/app/services/samples.py`, `backend/app/routers/samples.py`.

Sample GeoTIFFs live in `DATA_DIR/samples` (by default `backend/data/samples/`). Drop
`.tif`/`.tiff` files there or upload them. `.tif` files are ignored by git; only the
README, `.gitkeep` and `.json` sidecars are versioned.

## Ids

The id is the file stem turned into a slug: lowercase, characters outside
`[A-Za-z0-9_-]` become `-`. For example `S1 VV 2024.tif` becomes `s1-vv-2024`. Only ids
found by the folder scan map to files, so no path is built from user input. The scan is
cached by modification time (sidecars included).

## Acquisition date

The date is taken from the first source that has one:

1. Sidecar `<stem>.json`, field `datetime`.
2. TIFF tags: `TIFFTAG_DATETIME`, `ACQUISITION_DATE`, `DATE_TIME`, then any date-like key
   in any namespace.
3. File name: `YYYYMMDDTHHMMSS`, `YYYY-MM-DD` or `YYYYMMDD`.
4. Otherwise `datetime` is `null`.

`time_source` reports which one was used: `sidecar`, `tag:<ns>:<key>`, `filename` or
`none`. Years must be between 1900 and 2100.

Sidecar format (only `datetime` affects the date; the other fields are returned as is):

```json
{
  "datetime": "2025-11-03T12:00:00Z",
  "label": "Text for the UI",
  "sensor": "NISAR L-band",
  "polarization": "HH",
  "notes": "Free comment"
}
```

## Endpoints

- `GET /api/samples`: list, filtered by `bbox`, `start`, `end`. Sorted by date, undated
  last. TIFF tags are not included.
- `GET /api/samples/{id}`: full metadata including tags.
- `GET /api/samples/{id}/file`: the GeoTIFF.
- `GET /api/samples/{id}/preview.png`: reprojected to EPSG:3857 (a MapLibre image source
  is linear in Web Mercator), long side at most 1024 px. Single band uses a 2-98
  percentile grey stretch; three bands are RGB. Nodata, NaN and all-zero RGB are
  transparent. Header `X-Bounds-WGS84`.
- `POST /api/samples`: multipart `file` plus optional `datetime` and `label` (written to
  a sidecar). Returns 201. Not a `.tif`, not readable by rasterio, or no CRS: 422.
  Duplicate name: 409. Over 200 MB: 413.
