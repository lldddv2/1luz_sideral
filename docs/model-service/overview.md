# Overview

`model_service/water_unet/` is an independent process. It does not import any
backend code. It runs the U-Net water model (`NISAR_UNET_MODELO_V1`, trained on
Okavango HH backscatter) locally and talks to the backend through the
`/api/models` endpoints.

The design is **pull-based**: the client opens all connections, so the user's
machine needs no inbound ports. The backend only prepares input data, stores the
result, renders it and pushes updates to the frontend.

## Package layout

| File | Purpose |
|---|---|
| `model.py` | U-Net definition, weight loading, patch-wise prediction with Hann blending, `predict_db` (dB to power, then predict). |
| `client.py` | `Client.hello` / `step` / `run` loop, `infer_tif` (GeoTIFF in, GeoTIFF out), CLI `main`. |
| `__main__.py` | Entry point for `python -m water_unet`. |
| `unet_water_v1.pt`, `unet_water_v1.json` | Weights and normalization metadata (copied from the training run). |

## Model

- Architecture: U-Net, 1 input channel, 1 output channel, `base=16`, `depth=3`.
- Input: NISAR L2 GCOV `HHHH` gamma-0 linear power at 30 m, converted with
  `10*log10` and then z-scored (mean `-10.8395`, std `2.4847`).
- Inference: 64 px patches with 32 px overlap, blended with Hann weights.
- Output: water probability in `[0, 1]`. The metadata file stores a reference
  classification threshold of `0.97`.

## Contract with `/api/models`

Authentication: every model call sends `Authorization: Bearer <token>`. The token
is created by the web app (`POST /api/models/token`), lives in memory on the
backend, has a TTL of 2 hours and belongs to one web session. An invalid or
expired token returns `401`. The SSE stream uses `?token=` because `EventSource`
cannot set headers.

The model counts as *connected* while its `last_seen` timestamp (updated by
`hello` and `jobs/next`) is at most 30 s old.

### Client loop

1. `POST /api/models/hello` with
   `{"name": "water_unet_v1", "output": "probability", "label": "Agua", "pols": ["HH"]}`.
2. `GET /api/models/jobs/next`: long poll of up to 25 s.
   - `204`: no job, poll again.
   - `200`: `{job_id, bbox, date, pols, input_url}`. The job becomes `running`.
3. `GET input_url` (`/api/models/jobs/{id}/input.tif`). A relative URL is joined to
   the `--url` root.
4. Run inference.
5. `POST /api/models/jobs/{id}/result` as multipart field `file`.

### Input raster

GeoTIFF, float32, one band per requested polarization in job order. Each band
description is the polarization name. Values are in dB, 30 m pixels, in the
scene's UTM zone, with NaN as nodata. Tags: `scene_id`, `datetime`, `pols`,
`units=dB`. The first request prepares the raster (cold start 22 to 40 s); later
requests hit a cache keyed by polarizations. If no scene exists, or the scene
lacks a requested polarization, the job fails with a `404` that says what is
missing and what is available.

### Result raster

One-band float32 GeoTIFF on the same grid as the input, NaN as nodata. The client
copies the input profile and writes with deflate compression. The backend renders
it to a PNG in EPSG:3857 according to the declared `output`:

- `probability`: blue ramp, values `<= 0.05` transparent.
- `continuous`: viridis stretched p2 to p98, NaN transparent.
- `classes`: integer classes (at most 12 non-zero classes, otherwise `400`),
  Tableau palette by ascending value, `0`/NaN transparent.

### Other endpoints

| Endpoint | Caller | Notes |
|---|---|---|
| `POST /token` | web app | Returns `{token, expires_at}`. |
| `GET /status` | any | `{connected, name, output, label, units, pols, last_seen}`. |
| `POST /jobs` | web app | `{bbox: [w, s, e, n], date?}` returns `{job_id}`. A side over 60 km returns `400`. |
| `GET /jobs/{id}.png` | web app | Rendered PNG, no auth (hard-to-guess id). |
| `GET /events?token=` | web app | SSE: `status` and `job` events (state `queued`, `running`, `done`, `error`, plus stats, legend, `png_url`). |

`hello` accepts `pols` from `HH`, `HV`, `VV`, `VH` only (default `["HH"]`); other
values return `400`. The legacy body `kind: "water_prob"` without `output` maps
to `probability`.

### Error handling

- Errors inside one job are logged and the client keeps polling.
- Poll errors: wait 3 s, send `hello` again, continue.
- `401` stops the client with exit code 2.
