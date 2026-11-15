# Water detection (U-Net)

Code: `backend/app/water/` (`model.py`, `service.py`), `backend/app/routers/water.py`.

## Model

`NISAR_UNET_MODELO_V1`: a UNet with 1 input and 1 output channel, base 16, depth 3,
trained only on the Okavango delta. Weights are in `backend/app/water/unet_water_v1.pt`
(a plain `state_dict`, loaded with `weights_only=True`). The metadata file
`unet_water_v1.json` holds the normalisation (mean -10.8395, std 2.4847), the threshold
(0.97), patch size 64 and overlap 32.

## `POST /api/water`

Body: `{"bbox": [west, south, east, north], "date": "YYYY-MM-DD"?}` in EPSG:4326.

Pipeline:

1. Search CMR for the latest `NISAR_L2_GCOV_V1`/`BETA` scene on or before `date`.
2. Take the first three scenes and pick one with valid coverage of at least 0.5
   (frames are cut along track, so the newest may only touch a corner).
3. Read HHHH and the mask through HTTP range requests (4 MB blocks prefetched in
   parallel).
4. Keep mask values 1-254, average to 30 m in the scene's UTM zone, convert to dB
   (`10 log10`), normalise, and run the model with Hann-window tiling.

Response: `{id, scene_id, datetime, bounds, threshold, water_fraction, valid_fraction,
read_mb, timings, png_url}`. `GET /api/water/{id}.png` returns an EPSG:3857 PNG with a
blue ramp; probabilities at or below 0.05 are transparent.

Results are cached in `DATA_DIR/water/<hash(bbox, scene)>.{json,png}`. A cold 45 km
request takes about 22-40 s (mostly reading 50-110 MB; inference is about 2 s); a cached
one about 1 s.

## Errors

| Status | Cause |
|---|---|
| 400 | bbox side over 60 km, or invalid bbox |
| 404 | no scene found |
| 502 | Earthdata connection or HTTP error (401/403 means bad credentials), or other failure |
| 504 | Earthdata timeout |

## Dependencies

`torch` (CPU wheels; `pyproject.toml` configures the PyTorch CPU index for uv) and
`h5py`.
