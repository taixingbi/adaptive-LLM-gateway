"""Locust workload for the paper experiments.

Hits POST /v1/infer with SigV4. Token demand is sent as metadata; the gateway
builds the prompt so Locust does not ship 8k-token bodies on every request.

  GATEWAY_URL=https://xxxx.execute-api.us-east-1.amazonaws.com \
  PROMPT_CLASS=medium locust -f loadgen/locustfile.py --users 10 --spawn-rate 2
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from locust import HttpUser, between, task

from generate_tenants import tenants as load_tenants

ROOT = Path(__file__).resolve().parent
PROMPT_CLASS = os.environ.get("PROMPT_CLASS", "medium")
REGION = os.environ.get("AWS_REGION", "us-east-1")
_tenant_index = 0


def _load_prompt_meta() -> dict[str, dict]:
    prompts: dict[str, dict] = {}
    name = None
    for raw in (ROOT / "prompts" / "manifest.yaml").read_text(encoding="utf-8").splitlines():
        if raw.startswith("  ") and not raw.startswith("    ") and raw.strip().endswith(":"):
            name = raw.strip()[:-1]
            prompts[name] = {}
        elif name and ":" in raw:
            key, value = raw.strip().split(":", 1)
            value = value.strip()
            if key != "path":
                prompts[name][key] = int(value) if value.isdigit() else value
    return prompts


TENANTS = load_tenants()
PROMPTS = _load_prompt_meta()


class TenantUser(HttpUser):
    wait_time = between(0.2, 1.0)
    host = os.environ.get("GATEWAY_URL", "https://example.execute-api.us-east-1.amazonaws.com")

    def on_start(self) -> None:
        global _tenant_index
        session = boto3.Session(region_name=REGION)
        role_arn = os.environ.get("LOADGEN_ROLE_ARN")
        if role_arn:
            assumed = session.client("sts").assume_role(
                RoleArn=role_arn,
                RoleSessionName="locust-loadgen",
            )["Credentials"]
            session = boto3.Session(
                aws_access_key_id=assumed["AccessKeyId"],
                aws_secret_access_key=assumed["SecretAccessKey"],
                aws_session_token=assumed["SessionToken"],
                region_name=REGION,
            )
        creds = session.get_credentials().get_frozen_credentials()
        self._signer = SigV4Auth(creds, "execute-api", REGION)
        self._url = f"{self.host.rstrip('/')}/v1/infer"
        spec = PROMPTS[PROMPT_CLASS]
        self._body = {
            "tenant_id": TENANTS[_tenant_index % len(TENANTS)]["tenant_id"],
            "prompt_class": PROMPT_CLASS,
            "input_tokens": spec["input_tokens"],
            "max_tokens": spec["max_tokens"],
        }
        _tenant_index += 1

    @task
    def infer(self) -> None:
        payload = json.dumps(self._body, separators=(",", ":"))
        request = AWSRequest(
            method="POST",
            url=self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        self._signer.add_auth(request)
        self.client.post("/v1/infer", data=payload, headers=dict(request.headers), name="/v1/infer")
