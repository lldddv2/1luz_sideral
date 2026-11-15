# AWS 管線（NISAR GCOV 雲中裁）

- 區 us-west-2（ASF 桶同區，範圍讀免費）。帳號：free tier，唯准 t3.micro/small 等；t3.medium 拒（InvalidParameterCombination）。故預 t3.small，env INSTANCE_TYPE 可改。
- 本機 `uvx awscli` 呼 secretsmanager/IAM 掛死；用 boto3（backend venv）。
- 資源（皆 tag project=luz-sideral）：
  - 桶 `luz-sideral-nisar-9828`（阻公開）。ARN arn:aws:s3:::luz-sideral-nisar-9828
  - 密 `luz-sideral/earthdata`（Secrets Manager，JSON username/password，自 backend/.env）。ARN arn:aws:secretsmanager:us-west-2:<acct>:secret:luz-sideral/earthdata-6hGqs4
  - IAM role＋instance profile `luz-sideral-nisar-runner`；內策 runner：桶 Get/Put/List、該密 GetSecretValue。
  - SG `luz-sideral-noingress`（預設 VPC，無入規則）。
  - EC2 一次機（AL2023、IMDSv2、shutdown 即 terminate），名 luz-sideral-nisar-crop。
- 碼：backend/cloud/deploy.py（冪等建＋發機）、user_data.sh（裝依、取 code/nisar_crop.py、跑、傳日誌、關機）、nisar_crop.py（CMR 查 PR granules，s3credentials 暫憑，s3fs+h5py 範圍讀 frequencyA HHHH/HVHV，AOI bbox 窗，外遮 NaN，保 UTM 不重投，COG deflate float32 線性 gamma0）。座標假 x/yCoordinates 為像元心（半像元偏恐存，未驗）。
- 出：s3://桶/nisar/gcov/<granule>/{HH,HV}.tif、metadata.json；index.json 總之；logs/run-*.log。
- 重跑：`cd backend && uv run python cloud/deploy.py`（改 AOI/時則改 nisar_crop.py 常數）。
- 後端：env NISAR_BUCKET=luz-sideral-nisar-9828、AWS_REGION=us-west-2；/api/scenes/query 與 /{id}/data 之 source="nisar"，data 加 polarization HH|HV；讀 /vsis3/。碼 services/nisar_s3.py；index 快取 60 s；無桶 501，S3 敗 502。
- 拆：
  - `aws s3 rm s3://luz-sideral-nisar-9828 --recursive && aws s3api delete-bucket --bucket luz-sideral-nisar-9828`
  - `aws secretsmanager delete-secret --secret-id luz-sideral/earthdata --force-delete-without-recovery`
  - `aws iam remove-role-from-instance-profile --instance-profile-name luz-sideral-nisar-runner --role-name luz-sideral-nisar-runner; aws iam delete-instance-profile --instance-profile-name luz-sideral-nisar-runner; aws iam delete-role-policy --role-name luz-sideral-nisar-runner --policy-name runner; aws iam delete-role --role-name luz-sideral-nisar-runner`
  - `aws ec2 delete-security-group --group-id sg-0e2bf67e2b88003b9`（皆 --region us-west-2）
