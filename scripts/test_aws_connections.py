"""Verify local AWS configuration for the Bloomsmart Lambda services.

This is a read-only smoke test. It checks that the configured credentials can
describe the configured DynamoDB table and access the configured S3 bucket.

Run from the repository root:
    python aws-lambda/scripts/test_aws_connections.py
"""

from __future__ import annotations

import os
import sys
from typing import Final

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError


DEFAULT_REGION: Final[str] = "ap-southeast-2"
DEFAULT_DYNAMODB_TABLE: Final[str] = "felis-ai-marketing-bloomsmart-session"
S3_BUCKET_NAME: Final[str] = "aws-felis-ai-marketing-bloomsmart"


def _required_environment(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    joined_names = " or ".join(names)
    raise ValueError(f"Set {joined_names} before running this check.")


def _check_dynamodb(session: boto3.Session, table_name: str) -> None:
    client = session.client("dynamodb")
    response = client.describe_table(TableName=table_name)
    table = response["Table"]
    table_status = table.get("TableStatus", "unknown")
    print(f"DynamoDB: OK ({table_name}, status={table_status})")


def _check_s3(session: boto3.Session, bucket_name: str) -> None:
    client = session.client("s3")
    client.head_bucket(Bucket=bucket_name)
    print(f"S3: OK ({bucket_name})")


def main() -> int:
    region = os.getenv("AWS_REGION", DEFAULT_REGION).strip() or DEFAULT_REGION
    table_name = os.getenv("DYNAMODB_TABLE_SESSION", DEFAULT_DYNAMODB_TABLE).strip()

    try:
        bucket_name = _required_environment("S3_BUCKET_NAME", "AWS_S3_BUCKET_NAME")
        session = boto3.Session(region_name=region)
        if session.get_credentials() is None:
            raise NoCredentialsError(provider="environment or AWS profile")

        _check_dynamodb(session, table_name)
        _check_s3(session, bucket_name)
    except (ValueError, NoCredentialsError) as error:
        print(f"AWS configuration error: {error}", file=sys.stderr)
        return 1
    except (BotoCoreError, ClientError) as error:
        print(f"AWS connectivity/permission check failed: {error}", file=sys.stderr)
        return 1

    print(f"AWS checks passed in region {region}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
