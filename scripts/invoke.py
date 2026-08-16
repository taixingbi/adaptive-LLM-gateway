#!/usr/bin/env python3
"""SigV4 invoke of POST /v1/converse using the current AWS credentials."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="https://{api-id}.execute-api.{region}.amazonaws.com/v1/converse")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--model", default="nova-lite")
    parser.add_argument("--prompt", default="Reply with the word pong.")
    parser.add_argument("--profile")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    creds = session.get_credentials()
    if creds is None:
        print("No AWS credentials found. Use AWS_PROFILE or SSO.", file=sys.stderr)
        return 1
    frozen = creds.get_frozen_credentials()

    body = json.dumps(
        {
            "model": args.model,
            "messages": [{"role": "user", "content": [{"text": args.prompt}]}],
            "inferenceConfig": {"maxTokens": 64},
        }
    )
    request = AWSRequest(method="POST", url=args.url, data=body, headers={"Content-Type": "application/json"})
    SigV4Auth(frozen, "execute-api", args.region).add_auth(request)
    parsed = urlparse(args.url)
    prepared = request.prepare()
    http = URLLib3Session()
    response = http.send(prepared)
    print(f"status={response.status_code}")
    print(response.text)
    return 0 if response.status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
