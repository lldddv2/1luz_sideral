# Architecture

The repository has three components.

`frontend/`
: React + TypeScript single-page app built with Vite. It renders the map with MapLibre
  (`react-map-gl`) and the onboarding tour with `driver.js`. It talks to the backend only
  through HTTP calls to `/api/*`.

`backend/`
: FastAPI application (`app.main:app`). Routers are mounted under `/api` and cover
  health, NISAR scene search and extraction, samples, land cover, elevation (DEM),
  natural features, region search, surface water (U-Net inference) and the external
  model API. NISAR access uses `asf_search` and `harmony-py`; rasters are processed with
  `rasterio`, `numpy`, `shapely` and `pyproj`. When `STATIC_DIR` is set, the backend also
  serves the built frontend at `/`.

`model_service/`
: Standalone Python client (`python -m water_unet`) that runs the U-Net water model on
  the user's own machine. It connects to the backend with a token issued by the web app,
  pulls jobs over plain HTTP (no inbound ports needed) and uploads results. The web app
  follows job state through server-sent events.

## Data flow

```text
Browser (frontend)  --HTTP /api/*-->  FastAPI backend  --> NASA Earthdata / ASF (NISAR)
                                          ^
                                          |  pull jobs, upload results (token auth)
                                   model_service (user machine)
```

In production a single container holds the backend and the built frontend, so the app
and API share one origin and no CORS configuration is needed.
