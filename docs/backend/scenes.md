# Scenes

Code: `backend/app/services/scenes.py`, `backend/app/routers/scenes.py`.

A scene is one acquisition (one satellite pass) read from the samples folder
(`DATA_DIR/samples`). The service keeps no server state.

## `POST /api/scenes/query`

Body:

- `regions`: GeoJSON FeatureCollection, Feature, or Polygon/MultiPolygon in WGS84.
  Region ids come from `properties.id`, or default to `r1`, `r2`, ...
- `date`: ISO date. Keeps scenes within `window_days` (default 15, range 0-365).
- `start`, `end`: alternative time filter. Giving `date` together with `start`/`end`
  returns 422.

At most 10 regions and 5000 vertices in total, otherwise 422.

The response is a FeatureCollection. Each feature's geometry is the scene's WGS84
bounding box. Properties include `scene_id`, `acquired_at`, `time_source`,
`days_from_date` (with `date`), `regions` (`[{id, coverage_pct}]`, only those with
coverage above 0, as a WGS84 area ratio), `native_res_m`, `crs`, `count`, `dtype` and
`assets.data`.

Ordering: by absolute days from `date` when given, otherwise by `acquired_at`; scenes
with no date come last. Undated scenes are dropped when a time filter is used.

## `POST /api/scenes/{scene_id}/data`

Body:

| Field | Default | Notes |
|---|---|---|
| `geometry` | required | Polygon/MultiPolygon or Feature in WGS84 |
| `format` | `png` | `png`, `geotiff` or `json` |
| `width`, `height` | native | 16-2048. If one is missing it follows the aspect ratio. Native size is reduced when the long side exceeds 2048 |
| `fit` | `pad` | `pad` centres the data and fills the rest with nodata/alpha 0; `stretch` fills the box |
| `resampling` | `average` | `average`, `bilinear`, `nearest` |
| `mask` | `true` | mask pixels outside the geometry |

The total output is limited to 4194304 pixels. Unknown scene returns 404; a geometry that
does not intersect the scene returns 422.

Method: the region is transformed to the scene CRS, the window is the region bbox
intersected with the scene bounds, it is read with `from_bounds` and `out_shape`, and
`geometry_mask` masks it. There is no reprojection, not even for PNG (see the `X-Note`
header). SAR power should be averaged in the linear domain.

Response headers (all exposed for CORS): `X-Bounds-WGS84`, `X-Pixel-Size-M`,
`X-Out-Size`, `X-CRS`, `X-Corners-WGS84`.

- `geotiff`: deflate compression, original dtype, nodata (float NaN or int 0 when the
  source has none).
- `png`: 2-98 percentile stretch.
- `json`: `width`, `height`, `bands` (`min`, `max`, `mean`, `std`, `valid_pct`),
  `bounds_wgs84`, `pixel_size_m`, `crs`.
