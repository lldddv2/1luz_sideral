# Configuration

Settings are read by `app.config.Settings` (pydantic-settings) from environment variables
or from `backend/.env`. Copy `backend/.env.example` to `backend/.env` (never commit it) and
run uvicorn from `backend/`.

| Variable | Default | Purpose |
|---|---|---|
| `EARTHDATA_USERNAME` | unset | NASA Earthdata Login user |
| `EARTHDATA_PASSWORD` | unset | NASA Earthdata Login password |
| `NETRC` | unset | Path to a netrc file with Earthdata credentials, exported as `NETRC` for requests and harmony-py |
| `DATA_DIR` | `data` | Data folder: inventories, GeoTIFFs, SQLite job ledger, samples, water and model caches |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `STATIC_DIR` | unset | Built frontend directory to serve at `/` (production) |

## Earthdata credentials

Harmony uses `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` only when both are set. Setting
only one has no effect. Otherwise it uses `NETRC`, or `~/.netrc` as a fallback.

## Data layout

Under `DATA_DIR`:

- `nisar/`: extractor output and job ledger.
- `inventories/`: search inventories.
- `samples/`: sample GeoTIFFs (see {doc}`samples`).
- `water/`: U-Net result cache.
- `models/`: external model inputs, results and PNGs.
