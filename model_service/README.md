# luzsi model service: U-Net water

Standalone client that runs the U-Net water model (NISAR_UNET_MODELO_V1, trained on Okavango HH)
on your own machine and connects it to a luzsi backend over plain HTTP (pull model, no inbound ports).

## Install

```bash
cd model_service
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -r requirements.txt   # torch from the CPU wheel index
```

## Run

1. Open the web app, section "Modelo propio", and copy the token (valid 2 h).
2. Start the client:

```bash
python -m water_unet --url http://localhost:8000 --token <TOKEN>
# or: set LUZSI_URL / LUZSI_TOKEN and run `python -m water_unet`
```

The web app shows the model as connected; requested areas are processed automatically.
Exit code 2 means the token is invalid or expired: get a new one from the web app.

## Contract (all calls send `Authorization: Bearer <token>`)

1. `POST /api/models/hello` `{name, kind: "water_prob", pols: ["HH"]}`.
2. `GET /api/models/jobs/next` long poll (<= 25 s): `204` = nothing, poll again; `200` = `{job_id, bbox, date, input_url}`.
3. `GET input_url` (`/api/models/jobs/{id}/input.tif`): GeoTIFF float32, 1 band HH in dB, 30 m UTM, NaN = nodata.
4. Inference: dB -> z-score (mean -10.8395, std 2.4847), 64 px patches, overlap 32, Hann-weighted blending.
5. `POST /api/models/jobs/{id}/result` multipart `file` = GeoTIFF float32 water probability 0-1, same grid, NaN = nodata.

Job errors are logged and the client keeps polling; a `401` stops it.

## Test

```bash
python -m pytest
```

Checks agreement > 99 % with the reference classification (uses `backend/tests/data/water`) and one mocked client cycle.
