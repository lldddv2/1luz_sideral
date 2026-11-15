# Backend

The backend is a FastAPI application (`backend/app/`) that searches and reads NISAR
(NASA-ISRO SAR) data, serves local sample GeoTIFFs, runs a U-Net water detector and
bridges to external models that run on the user's machine. All routes live under the
`/api` prefix.

```{toctree}
:maxdepth: 2

rest-api
scenes
samples
water
external-models
configuration
testing
api-reference
```

## Running locally

Run uvicorn from the `backend/` directory so the relative `DATA_DIR` and `.env` resolve:

```bash
cd backend
cp .env.example .env   # then fill in Earthdata credentials
uvicorn app.main:app --reload
```

The interactive OpenAPI docs are then at `http://localhost:8000/docs`.
