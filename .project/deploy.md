# 部署（AWS Lightsail 容器）

- 一鏡像：根 `Dockerfile` 二段（node 建 frontend/dist；python3.12-slim 裝 torch CPU + backend，`STATIC_DIR=/app/static` 則 FastAPI 掛 `/` 供前端）。同源，無 CORS 之需。`.dockerignore` 除 node_modules/.env/data/water/data/models。須 libexpat1（rasterio）。
- App Runner 拒（SubscriptionRequiredException：帳戶不許新用）；故用 Lightsail container service `luzsi`（micro，1 GB，scale 1，us-east-1）。勿 S3。
- 鏡像：ECR `317538169828.dkr.ecr.us-east-1.amazonaws.com/luzsi`，tag 為時戳。Lightsail ecrImagePullerRole 已啟，ECR repo policy 許之。
- 秘：SSM SecureString `/luzsi/EARTHDATA_USERNAME|PASSWORD`；Lightsail 不支 SSM 引，部署時腳本讀之入容器 env（不印、不入 git）。
- 命：`scripts/deploy_lightsail.sh`（需 docker 守護行、~/.aws 憑；無 aws 則用 `uvx --from awscli aws`）。印服務 URL。
- URL：https://luzsi.82fhra512x0gc.us-east-1.cs.amazonlightsail.com/（前端 `/`，API `/api/*`，健 `/api/health`）。
- 遺：IAM 角 luzsi-apprunner-ecr、luzsi-apprunner-instance 為 App Runner 試所建，今無用，可刪。data/ 於容器內，重部署則失 water 快取。
