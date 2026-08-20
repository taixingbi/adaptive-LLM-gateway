"""Locust workload driven by experiments/*.yaml via EXPERIMENT_FILE."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import boto3
import yaml
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from locust import HttpUser, events, task

from traffic import burst_multiplier

ROOT = Path(__file__).resolve().parent
REGION = os.environ.get("AWS_REGION", "us-east-1")
_tenant_index = 0
_TEST_START: float | None = None
_PROFILES: list[dict] = []
_SCENARIO: dict = {}


@events.test_start.add_listener
def _on_test_start(environment, **kwargs) -> None:
    global _TEST_START
    _TEST_START = time.time()


def _elapsed_s() -> float:
    if _TEST_START is None:
        return 0.0
    return time.time() - _TEST_START


def _load_prompts() -> dict[str, dict]:
    raw = yaml.safe_load((ROOT / "prompts" / "manifest.yaml").read_text(encoding="utf-8"))
    prompts: dict[str, dict] = {}
    for name, spec in (raw.get("prompts") or {}).items():
        entry = dict(spec)
        entry["text"] = (ROOT / "prompts" / spec["path"]).read_text(encoding="utf-8")
        prompts[name] = entry
    return prompts


def _init_scenario() -> None:
    global _PROFILES, _SCENARIO
    path = os.environ.get("EXPERIMENT_FILE")
    if path:
        _SCENARIO = json.loads(Path(path).read_text(encoding="utf-8"))
        _PROFILES = _SCENARIO["profiles"]
        return
    from generate_tenants import tenants
    from traffic import assign_traffic

    n = int(os.environ.get("TENANT_LIMIT", "100"))
    _PROFILES = assign_traffic(tenants()[:n])
    _SCENARIO = {"victim": None, "phases": [], "run_id": os.environ.get("RUN_ID", "local")}


_init_scenario()
PROMPTS = _load_prompts()


class TenantUser(HttpUser):
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
        self._profile = _PROFILES[_tenant_index % len(_PROFILES)]
        _tenant_index += 1

    def wait_time(self) -> float:
        return 60.0 / max(self._effective_rpm(), 0.05)

    def _effective_rpm(self) -> float:
        rpm = float(self._profile["rpm"])
        victim = _SCENARIO.get("victim")
        if victim and self._profile["tenant_id"] == victim:
            rpm *= burst_multiplier(_elapsed_s(), _SCENARIO.get("phases") or [])
        return rpm

    def _prompt_phase(self) -> dict | None:
        token_phases = _SCENARIO.get("token_phases") or []
        if not token_phases:
            return None
        width = float(_SCENARIO.get("phase_duration_s") or 180)
        idx = min(int(_elapsed_s() // width), len(token_phases) - 1)
        return token_phases[idx]

    def _prompt_class(self) -> str:
        phase = self._prompt_phase()
        if phase:
            return phase["prompt_class"]
        forced = _SCENARIO.get("prompt_class")
        return forced or self._profile["prompt_class"]

    @task
    def infer(self) -> None:
        prompt_class = self._prompt_class()
        spec = dict(PROMPTS[prompt_class])
        phase = self._prompt_phase()
        if phase:
            if phase.get("input_tokens") is not None:
                spec["input_tokens"] = int(phase["input_tokens"])
            if phase.get("max_tokens") is not None:
                spec["max_tokens"] = int(phase["max_tokens"])
        body = {
            "tenant_id": self._profile["tenant_id"],
            "prompt_class": prompt_class,
            "prompt": spec["text"],
            "input_tokens": spec["input_tokens"],
            "max_tokens": spec["max_tokens"],
            "run_id": _SCENARIO.get("run_id") or os.environ.get("RUN_ID", "local"),
        }
        payload = json.dumps(body, separators=(",", ":"))
        request = AWSRequest(
            method="POST",
            url=self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        self._signer.add_auth(request)
        with self.client.post(
            "/v1/infer",
            data=payload,
            headers=dict(request.headers),
            name="/v1/infer",
            catch_response=True,
        ) as response:
            # Admission REJECT/QUEUE-full are experiment outcomes, not Locust errors.
            if response.status_code in {200, 429, 503}:
                response.success()
            else:
                response.failure(f"{response.status_code}: {response.text[:200]}")
