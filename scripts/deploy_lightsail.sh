#!/usr/bin/env bash
# Build the single image (frontend + backend) and deploy it to the Lightsail
# container service "luzsi". Earthdata credentials are read from SSM
# Parameter Store (/luzsi/EARTHDATA_*) at deploy time; they are never stored in git.
set -euo pipefail
cd "$(dirname "$0")/.."
aws() { if type -P aws >/dev/null; then command aws "$@"; else uvx --from awscli aws "$@"; fi; }
REGION=${AWS_REGION:-us-east-1}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REPO=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/luzsi
TAG=$(date +%Y%m%d%H%M%S)

DOCKER_BUILDKIT=0 docker build -t "$REPO:$TAG" .
aws ecr get-login-password --region "$REGION" | docker login -u AWS --password-stdin "${REPO%/*}"
docker push "$REPO:$TAG"

param() { aws ssm get-parameter --region "$REGION" --with-decryption --name "$1" --query Parameter.Value --output text; }
CONTAINERS=$(python3 - "$REPO:$TAG" "$(param /luzsi/EARTHDATA_USERNAME)" "$(param /luzsi/EARTHDATA_PASSWORD)" <<'PY'
import json, sys
image, user, password = sys.argv[1:4]
print(json.dumps({"app": {"image": image, "ports": {"8000": "HTTP"}, "environment": {
    "DATA_DIR": "/app/data", "STATIC_DIR": "/app/static",
    "EARTHDATA_USERNAME": user, "EARTHDATA_PASSWORD": password}}}))
PY
)
aws lightsail create-container-service-deployment --region "$REGION" --service-name luzsi \
  --containers "$CONTAINERS" \
  --public-endpoint '{"containerName":"app","containerPort":8000,"healthCheck":{"path":"/api/health"}}' \
  --query containerService.url --output text
