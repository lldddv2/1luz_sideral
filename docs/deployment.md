# Deployment

The app is deployed as one Docker image on an AWS Lightsail container service.

## Docker image

The root `Dockerfile` has two stages:

1. `node:22-slim` installs frontend dependencies and runs `npm run build`.
2. `python:3.12-slim` installs `libexpat1` (needed by `rasterio`), CPU-only `torch`
   and the backend package, copies `backend/data` and the built frontend into
   `/app/static`.

The container runs `uvicorn app.main:app` on port `8000`, with
`STATIC_DIR=/app/static` and `DATA_DIR=/app/data`. `.dockerignore` excludes
`node_modules`, `.env` files and local data and model caches.

Build and run locally:

```bash
docker build -t luzsi .
docker run --rm -p 8000:8000 --env-file backend/.env luzsi
```

## Lightsail

`scripts/deploy_lightsail.sh` builds the image, pushes it to Amazon ECR with a
timestamp tag and creates a new deployment of the Lightsail container service `luzsi`
(region from `AWS_REGION`, default `us-east-1`). The public endpoint health check uses
`/api/health`. The script prints the service URL.

Prerequisites:

- a running Docker daemon,
- AWS credentials in `~/.aws` (the AWS CLI is used if installed, otherwise it runs
  through `uvx --from awscli aws`),
- an ECR repository and a Lightsail container service with permission to pull from it.

```bash
scripts/deploy_lightsail.sh
```

## Secrets

Earthdata credentials are stored as SSM Parameter Store SecureString parameters
(`/luzsi/EARTHDATA_USERNAME` and `/luzsi/EARTHDATA_PASSWORD`). Lightsail cannot
reference SSM directly, so the deploy script reads them at deploy time and passes them
as container environment variables. They are never printed or stored in git.

## Notes

- Data under `/app/data` lives inside the container; a redeploy clears cached water
  results.
