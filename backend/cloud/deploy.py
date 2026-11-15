"""Create (idempotently) bucket, Earthdata secret, IAM role and launch a one-shot EC2 crop run.

Usage (from backend/):  uv run python cloud/deploy.py
Needs the default AWS profile and backend/.env with EARTHDATA_USERNAME/PASSWORD.
Prints only resource ids, never credentials.
"""
import json
import os
import time
from pathlib import Path

import boto3
import botocore.config

boto3.setup_default_session()
_CFG = botocore.config.Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 3})
from botocore.exceptions import ClientError

REGION = "us-west-2"
HERE = Path(__file__).resolve().parent
ROLE = "luz-sideral-nisar-runner"
SECRET = "luz-sideral/earthdata"
SG_NAME = "luz-sideral-noingress"
TAGS = [{"Key": "project", "Value": "luz-sideral"}]


def env_file():
    out = {}
    for line in (HERE.parent / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


def main():
    account = boto3.client("sts", config=_CFG).get_caller_identity()["Account"]
    bucket = f"luz-sideral-nisar-{account[-4:]}"
    s3 = boto3.client("s3", region_name=REGION, config=_CFG)
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": TAGS})
    print("bucket", bucket)

    sm = boto3.client("secretsmanager", region_name=REGION, config=_CFG)
    try:
        secret_arn = sm.describe_secret(SecretId=SECRET)["ARN"]
    except ClientError:
        e = env_file()
        secret_arn = sm.create_secret(Name=SECRET, Tags=TAGS, SecretString=json.dumps(
            {"username": e["EARTHDATA_USERNAME"], "password": e["EARTHDATA_PASSWORD"]}))["ARN"]
    print("secret", secret_arn.split(":")[-1])

    iam = boto3.client("iam", config=_CFG)
    try:
        iam.get_role(RoleName=ROLE)
    except ClientError:
        iam.create_role(RoleName=ROLE, Tags=TAGS, AssumeRolePolicyDocument=json.dumps({
            "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"},
                                                    "Action": "sts:AssumeRole"}]}))
        iam.create_instance_profile(InstanceProfileName=ROLE, Tags=TAGS)
        iam.add_role_to_instance_profile(InstanceProfileName=ROLE, RoleName=ROLE)
        time.sleep(15)  # instance profile propagation
    iam.put_role_policy(RoleName=ROLE, PolicyName="runner", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["s3:PutObject", "s3:GetObject"], "Resource": f"arn:aws:s3:::{bucket}/*"},
            {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{bucket}"},
            {"Effect": "Allow", "Action": "secretsmanager:GetSecretValue", "Resource": secret_arn}]}))
    print("role", ROLE)

    s3.upload_file(str(HERE / "nisar_crop.py"), bucket, "code/nisar_crop.py")

    ssm = boto3.client("ssm", region_name=REGION, config=_CFG)
    ami = ssm.get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")["Parameter"]["Value"]
    ec2 = boto3.client("ec2", region_name=REGION, config=_CFG)
    vpc = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]["VpcId"]
    groups = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [SG_NAME]},
                                                   {"Name": "vpc-id", "Values": [vpc]}])["SecurityGroups"]
    if groups:
        sg = groups[0]["GroupId"]
    else:
        sg = ec2.create_security_group(GroupName=SG_NAME, Description="egress only, no ingress", VpcId=vpc,
                                       TagSpecifications=[{"ResourceType": "security-group", "Tags": TAGS}])["GroupId"]
    user_data = (HERE / "user_data.sh").read_text().replace("__BUCKET__", bucket)
    for attempt in range(3):
        try:
            inst = ec2.run_instances(
                ImageId=ami, InstanceType=os.environ.get("INSTANCE_TYPE", "t3.small"), MinCount=1, MaxCount=1, SecurityGroupIds=[sg],
                IamInstanceProfile={"Name": ROLE}, InstanceInitiatedShutdownBehavior="terminate", UserData=user_data,
                MetadataOptions={"HttpTokens": "required"},
                TagSpecifications=[{"ResourceType": "instance", "Tags": TAGS + [{"Key": "Name", "Value": "luz-sideral-nisar-crop"}]},
                                   {"ResourceType": "volume", "Tags": TAGS}])["Instances"][0]["InstanceId"]
            break
        except ClientError as error:  # instance profile not yet visible to EC2
            if attempt == 2:
                raise
            print("retry run_instances:", error.response["Error"]["Code"])
            time.sleep(15)
    print("instance", inst, "sg", sg, "ami", ami)


if __name__ == "__main__":
    main()
