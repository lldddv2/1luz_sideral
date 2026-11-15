# Running the model service

## Install

```bash
cd model_service
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # torch comes from the CPU wheel index
```

Dependencies: `torch` (CPU wheels), `numpy`, `rasterio`, `requests`, `pytest`.

## Run

1. Open the web app, section **Your model**, and copy the token (valid 2 h).
2. Start the client:

```bash
python -m water_unet --url http://localhost:8000 --token <TOKEN>
```

The web app then shows the model as connected. Requested areas are processed
automatically.

## Parameters

| Flag | Environment variable | Default | Meaning |
|---|---|---|---|
| `--url` | `LUZSI_URL` | `http://localhost:8000` | Backend root URL. |
| `--token` | `LUZSI_TOKEN` | none (required) | Bearer token from the web app. |

Without a token the CLI exits with a usage error.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Normal stop (for example `Ctrl+C`). |
| `2` | Token invalid or expired (`401`). Get a new token from the web app. |

## Tests

```bash
cd model_service
python -m pytest
```

`pytest.ini` sets `pythonpath = .`. The tests check:

- Agreement above 99 % with the reference classification, using the data in
  `backend/tests/data/water`.
- One full client cycle against a mocked session, plus the `204` (no job) and
  `401` (stop) paths.
