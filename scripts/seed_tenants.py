#!/usr/bin/env python3
"""Write TenantPolicy items to DynamoDB. 100 logical tenants, one AWS account."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "loadgen"))
from generate_tenants import tenants  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default="bedrock-platform-dev-tenants")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    items = tenants()
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    print(f"seeded {len(items)} tenants into {args.table}")


if __name__ == "__main__":
    main()
