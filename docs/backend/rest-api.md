# REST API

All endpoints are mounted under `/api`. Bodies are JSON unless noted. Errors use the
FastAPI shape `{"detail": "..."}`.

## Health

| Method | Path | Params | Response |
|---|---|---|---|
| GET | `/api/health` | none | `{"status": "ok"}` |

## NISAR search, extraction and sizing

| Method | Path | Params | Response |
|---|---|---|---|
| POST | `/api/search` | body `{geometry, start, end, max_results=100}` (ISO-8601 with timezone; `max_results` 1-200) | `{inventory_id, products: [...]}`; each product has `product_id`, `product_type`, acquisition times, `geometry`, sizes, `variables`, `track`, `direction`, `frame`. 422 bad geometry, 400 bad input |
| POST | `/api/jobs` | body `{inventory_id, product_ids, variables, output_crs?}` | 202 `Job` (`id`, `state` queued/running/done/failed, `request`, `results`, `error`, timestamps). 404 unknown inventory, 400 product not in inventory |
| GET | `/api/jobs` | none | list of `Job` |
| GET | `/api/jobs/{job_id}` | path `job_id` | `Job`; 404 unknown |
| GET | `/api/jobs/{job_id}/files/{index}` | path `index` into the job's output files | GeoTIFF file; 404 when missing |
| POST | `/api/estimate` | body `{geometry, variables=1, products=1, spacing_m=10, bytes_per_pixel=4, inventory_id?}` | `{area_km2, bbox_km, pixels, per_file_bytes, total_bytes, human, assumptions, full_granules_bytes}`. No network calls |

## Scenes

See {doc}`scenes`.

| Method | Path | Params | Response |
|---|---|---|---|
| POST | `/api/scenes/query` | body `{regions, date?, window_days=15, start?, end?}` | GeoJSON FeatureCollection of scene footprints |
| POST | `/api/scenes/{scene_id}/data` | body `{geometry, format=png\|geotiff\|json, width?, height?, fit=pad\|stretch, resampling=average\|bilinear\|nearest, mask=true}` | PNG, GeoTIFF or JSON stats, plus `X-*` headers |

## Samples

See {doc}`samples`.

| Method | Path | Params | Response |
|---|---|---|---|
| GET | `/api/samples` | query `bbox=minx,miny,maxx,maxy`, `start`, `end` | `{items: [...]}` |
| GET | `/api/samples/{sample_id}` | path | full metadata including TIFF tags |
| GET | `/api/samples/{sample_id}/file` | path | the GeoTIFF |
| GET | `/api/samples/{sample_id}/preview.png` | path | PNG in EPSG:3857, header `X-Bounds-WGS84` |
| POST | `/api/samples` | multipart `file`, optional `datetime`, `label` | 201 metadata; 409 duplicate, 413 > 200 MB, 422 invalid |

## Natural features catalog

| Method | Path | Params | Response |
|---|---|---|---|
| GET | `/api/features/categories` | none | `[{key, name, count}]` |
| GET | `/api/features` | query `q`, `category`, repeatable `bbox=minx,miny,maxx,maxy` | features without `geometry`; 422 bad bbox |
| POST | `/api/features/search` | body `{q, category, areas: [GeoJSON geometry]}` | features whose outline intersects any area; 422 bad geometry |
| GET | `/api/features/{feature_id}` | path | one feature with `geometry`; 404 unknown |

When `q` matches a category word (Spanish or English, accents ignored) the whole
category is returned. Otherwise names are matched by prefix, then word prefix, then
substring. The catalog is `backend/app/data/features.json`, generated from Natural Earth
by `backend/scripts/build_features.py`.

## Administrative regions

| Method | Path | Params | Response |
|---|---|---|---|
| GET | `/api/regions` | query `q` (2-120 chars), `viewbox=west,south,east,north` optional | `[{id, name, label, type, bbox, geometry}]`; 422 bad viewbox, 502 Nominatim error |

This proxies OpenStreetMap Nominatim. Calls are serialized to at most one per second,
and results are kept in an in-memory LRU cache of 256 queries. Regions with polygons
come first, administrative ones before other places. Geometries are simplified to about
0.3% of the bbox span.

## Land cover (ESA WorldCover)

| Method | Path | Params | Response |
|---|---|---|---|
| GET | `/api/landcover/classes` | none | `[{code, key, name, name_en, color}]` |
| POST | `/api/landcover/stats` | body `{geometry}` | `{total_km2, nodata_km2, resolution_m, classes}` |
| POST | `/api/landcover/mask` | body `{geometry, classes, max_px=1024}` | mask PNG with `bounds` |

422 for bad geometry, AOI too large or unknown class; 502 when a tile cannot be read.

## DEM

| Method | Path | Params | Response |
|---|---|---|---|
| GET | `/api/dem/metadata` | query `lat`, `lon` | tile metadata |
| GET | `/api/dem/file` | query `lat`, `lon` | streamed GeoTIFF tile |
| GET | `/api/dem/crop` | query `bbox=minx,miny,maxx,maxy` | GeoTIFF crop |

404 missing tile, 422 bad input, 502 read failure.

## Water (U-Net)

See {doc}`water`.

| Method | Path | Params | Response |
|---|---|---|---|
| POST | `/api/water` | body `{bbox: [w,s,e,n], date?}` | `{id, scene_id, datetime, bounds, threshold, water_fraction, valid_fraction, read_mb, timings, png_url}` |
| GET | `/api/water/{key}.png` | path, 16 hex chars | PNG overlay |

## External models

See {doc}`external-models`.

| Method | Path | Auth | Response |
|---|---|---|---|
| POST | `/api/models/token` | none | `{token, expires_at}` |
| POST | `/api/models/hello` | Bearer | `{ok: true}` |
| GET | `/api/models/status` | Bearer | session status |
| POST | `/api/models/jobs` | Bearer | `{job_id}` |
| GET | `/api/models/jobs/next` | Bearer | job (200) or 204 |
| GET | `/api/models/jobs/{job_id}/input.tif` | Bearer | GeoTIFF |
| POST | `/api/models/jobs/{job_id}/result` | Bearer | `{ok, png_url}` |
| GET | `/api/models/jobs/{job_id}.png` | none | PNG |
| GET | `/api/models/events?token=` | query token | Server-Sent Events |

## Static frontend

When the `STATIC_DIR` environment variable points to a directory (the built
`frontend/dist`), it is mounted at `/` so the API and the frontend share one origin.
