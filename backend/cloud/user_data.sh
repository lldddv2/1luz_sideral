#!/bin/bash
# One-shot NISAR crop runner. Logs go to s3://$BUCKET/logs/, then the instance powers off (terminates).
BUCKET=__BUCKET__
exec > /var/log/nisar_crop.log 2>&1
set -x
trap 'aws s3 cp /var/log/nisar_crop.log s3://$BUCKET/logs/run-$(date -u +%Y%m%dT%H%M%SZ).log --region us-west-2; shutdown -h now' EXIT
dnf install -y python3.11 python3.11-pip
python3.11 -m pip install --quiet h5py s3fs rasterio pyproj shapely boto3 requests numpy
aws s3 cp s3://$BUCKET/code/nisar_crop.py /opt/nisar_crop.py --region us-west-2
NISAR_BUCKET=$BUCKET timeout 3000 python3.11 /opt/nisar_crop.py
