# Getting started

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 22 and npm
- A NASA Earthdata account (for downloading NISAR data)

## Backend

```bash
cd backend
cp .env.example .env   # then fill in the values
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000
```

The API is served under `/api`. Check it with:

```bash
curl http://localhost:8000/api/health
```

Run the tests with:

```bash
uv run pytest
```

### Environment variables

Configure these in `backend/.env` (see `backend/.env.example`):

`EARTHDATA_USERNAME`
: NASA Earthdata login user name.

`EARTHDATA_PASSWORD`
: NASA Earthdata login password.

`DATA_DIR`
: Directory for downloaded and cached data.

`CORS_ORIGINS`
: Allowed browser origins for the API during local development.

Never commit the `.env` file.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Other scripts: `npm run build` (type check and production build into `frontend/dist`)
and `npm run preview`.

## Model service (optional)

See {doc}`model-service/index` for running the standalone U-Net water client.

## Building these docs

```bash
pip install -r docs/requirements.txt
sphinx-build -b html docs docs/_build/html
```
