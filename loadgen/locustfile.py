"""Locust workload for the paper experiments.

Hits POST /v1/infer with SigV4. Known token demand is sent in the body so the
gateway does not call CountTokens on the hot path.

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

ROOT = Path(__file__).resolve().parent
PROMPT_CLASS = os.environ.get("PROMPT_CLASS", "medium")
REGION = os.environ.get("AWS_REGION", "us-east-1")
_tenant_index = 0


def _load_yaml_tenants(path: Path) -> list[dict]:
    items: list[dict] = []
    current: dict | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("  - tenant_id:"):
            if current:
                items.append(current)
            current = {"tenant_id": line.split(":", 1)[1].strip()}
        elif current and line.startswith("    ") and ":" in line:
            key, value = line.strip().split(":", 1)
            value = value.strip()
            current[key] = int(value) if value.lstrip("-").isdigit() else value
    if current:
        items.append(current)
    return items


def _load_prompts() -> dict[str, dict]:
    manifest = ROOT / "prompts" / "manifest.yaml"
    prompts: dict[str, dict] = {}
    name = None
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if raw.startswith("  ") and not raw.startswith("    ") and raw.strip().endswith(":"):
            name = raw.strip()[:-1]
            prompts[name] = {}
        elif name and ":" in raw:
            key, value = raw.strip().split(":", 1)
            value = value.strip()
            prompts[name][key] = int(value) if value.isdigit() else value
    for spec in prompts.values():
        spec["text"] = (ROOT / "prompts" / spec["path"]).read_text(encoding="utf-8")
    return prompts


TENANTS = _load_yaml_tenants(ROOT / "tenants.yaml")
PROMPTS = _load_prompts()


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
        self.credentials = session.get_credentials().get_frozen_credentials()
        self.tenant = TENANTS[_tenant_index % len(TENANTS)]
        _tenant_index += 1

    @task
    def infer(self) -> None:
        spec = PROMPTS[PROMPT_CLASS]
        body = {
            "tenant_id": self.tenant["tenant_id"],
            "prompt_class": PROMPT_CLASS,
            "input_tokens": spec["input_tokens"],
            "max_tokens": spec["max_tokens"],
            "prompt": spec["text"],
        }
        url = f"{self.host.rstrip('/')}/v1/infer"
        payload = json.dumps(body)
        request = AWSRequest(
            method="POST",
            url=url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        SigV4Auth(self.credentials, "execute-api", REGION).add_auth(request)
        self.client.post("/v1/infer", data=payload, headers=dict(request.headers), name="/v1/infer")
