# External models (`/api/models`)

Code: `backend/app/routers/models.py`, `backend/app/models_api/store.py`,
`backend/app/models_api/raster.py`. A reference client is in `model_service/water_unet/`.

The model runs as a separate process on the user's machine and talks to the backend over
plain HTTP using a pull pattern: a job queue plus Server-Sent Events. There is no
WebSocket, so a model can be tested with `curl`. The backend only prepares input data,
receives results, renders them and pushes updates to the frontend.

## Authentication

- `POST /api/models/token` creates a token (`secrets.token_urlsafe(24)`), kept in memory
  with a 2 h TTL. One token is one web page session.
- Model calls send `Authorization: Bearer <token>`.
- The SSE endpoint takes `?token=` because `EventSource` cannot set headers.
- Missing, invalid or expired token: 401.
- A model counts as connected when it was last seen (on `hello` or `jobs/next`) at most
  30 s ago.

## Flow

1. The page calls `POST /token` and shows the token to the user.
2. The model calls `POST /hello` with `{name, output, pols?, label?, units?}`.
   - `output`: `probability`, `continuous` or `classes`.
   - `pols` defaults to `["HH"]`; only `HH`, `HV`, `VV`, `VH` are accepted (other values
     return 400).
   - Legacy `kind: "water_prob"` without `output` means `probability`.
3. The page calls `POST /jobs` with `{bbox: [w,s,e,n], date?}` and gets `{job_id}`. A side
   over 60 km returns 400. The job copies the session's `pols`, `output`, `label` and
   `units`.
4. The model long-polls `GET /jobs/next` (up to 25 s; `last_seen` is refreshed every
   10 s). It returns 200 `{job_id, bbox, date, pols, input_url}` and the job becomes
   `running`, or 204 when nothing is queued.
5. The model downloads `GET /jobs/{id}/input.tif`.
6. The model uploads `POST /jobs/{id}/result` (multipart field `file`).
7. The page follows progress on `GET /events?token=`.

`GET /status` (Bearer) returns `{connected, name, output, label, units, pols, last_seen}`.

## Input raster

`input.tif` is a float32 GeoTIFF, one band per requested polarisation in job order, each
band's description is the polarisation name. Values are dB at 30 m in the scene's UTM
zone, nodata is NaN. Tags: `scene_id`, `datetime`, `pols`, `units=dB`. Scene selection,
reading, masking, averaging and `10 log10` follow the same method as
`backend/app/water/service.py`.

The first request builds the file (cold, about 20-40 s); later requests are served from
the cache `DATA_DIR/models/<hash(bbox, date, pols)>.{tif,json}`. If no scene exists or the
scene lacks a requested polarisation, the job fails and the request returns 404 with a
message naming what is missing and what is available.

## Result raster

The result must be a single-band float32 GeoTIFF on the same grid as the input (shape,
CRS and transform are checked). The backend renders an EPSG:3857 PNG according to
`output`:

- `probability`: blue ramp, values at or below 0.05 transparent.
- `continuous`: viridis over the 2nd-98th percentile, NaN transparent.
- `classes`: integer classes, at most 12 non-zero classes (more returns 400), Tableau
  palette in ascending value order, 0 and NaN transparent.

The job becomes `done` and the PNG is at `GET /jobs/{id}.png` (`DATA_DIR/models/<id>.png`,
no auth; ids are hard to guess).

## Events (SSE)

- `event: status`, data `{connected, name, output, label, units, pols}`.
- `event: job`, data `{job_id, state, output, label, units, pols, scene_id?, datetime?,
  bounds?, stats?, legend?, png_url?, error?}`. `state` is `queued`, `running`, `done` or
  `error`. `stats` is `{min, max, mean, fraction?}`; `fraction` (share of valid pixels
  with p >= 0.5) is present only for `probability`. `legend` is `{min, max}` or
  `{classes: [{value, color}]}`.

Every 10 s the stream sends a `status` event if the connection state changed, otherwise a
`: ping` comment.

## Internals

- `Store` holds sessions and jobs in memory. Each token has two `asyncio.Queue`s:
  `pending` (jobs for the model) and `events` (for SSE).
- `raster.build_input` reads any of HH/HV/VV/VH in one pass and reuses the water service's
  search and remote-read helpers. `raster.render_result` validates and renders results.

## Errors

| Status | Cause |
|---|---|
| 400 | invalid `pols` in `hello`; bbox over 60 km; invalid result raster or grid mismatch (job error); too many classes |
| 401 | missing or expired token |
| 404 | job not found for this token; no scene or missing polarisation (job error) |
| 409 | result sent before `input.tif` was fetched |
| 502 | Earthdata or input preparation failure (job error) |
