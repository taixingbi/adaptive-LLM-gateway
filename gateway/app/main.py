from __future__ import annotations

import asyncio
import json
import logging
import time
from functools import lru_cache
from typing import Any

import boto3
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.admission.base import Decision, RequestContext, get_policy
from app.auth import assert_model_allowed, caller_arn_from_headers
from app.bedrock import converse_stream
from app.config import get_settings
from app.counters import QuotaCounters, build_counters
from app.metrics import ResultWriter
from app.models import extract_usage, load_model_map, resolve_profile
from app.store import consume_quota, get_app_by_principal
from app.tenants import get_tenant
from app.usage import emit_usage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="bedrock-platform LLM Gateway", version="0.2.0")
settings = get_settings()
model_map = load_model_map(settings.model_map_json)
policy = get_policy(settings.admission_policy)
USE_BUCKETS = policy.name == "token-bucket"
counters: QuotaCounters = build_counters(settings.redis_url)

session = boto3.Session(region_name=settings.aws_region)
dynamodb = session.resource("dynamodb")
apps_table = dynamodb.Table(settings.apps_table)
rate_table = dynamodb.Table(settings.rate_limits_table)
tenants_table = dynamodb.Table(settings.tenants_table)
bedrock = session.client("bedrock-runtime")
cloudwatch = session.client("cloudwatch")
s3 = session.client("s3")
results = ResultWriter(s3, settings.results_bucket, settings.run_id)

PROMPT_CLASSES = {
    "short": {"input_tokens": 250, "max_tokens": 64},
    "medium": {"input_tokens": 2000, "max_tokens": 256},
    "long": {"input_tokens": 8000, "max_tokens": 1024},
}


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "policy": policy.name,
        "platform_tpm_budget": str(settings.platform_tpm_budget),
    }


@app.post("/v1/converse")
def converse(payload: dict[str, Any], request: Request) -> JSONResponse:
    caller = caller_arn_from_headers(
        {k.lower(): v for k, v in request.headers.items()},
        settings.caller_arn_header,
    )
    model_alias = payload.get("model")
    messages = payload.get("messages")
    if not model_alias or not messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body must include 'model' and 'messages'",
        )

    app_record = get_app_by_principal(apps_table, caller)
    assert_model_allowed(app_record, model_alias)
    profile_arn = resolve_profile(model_map, model_alias)

    inference_config = payload.get("inferenceConfig") or {"maxTokens": 256}
    token_estimate = int(inference_config.get("maxTokens") or 256)
    consume_quota(rate_table, app_record, token_estimate)

    kwargs: dict[str, Any] = {
        "modelId": profile_arn,
        "messages": messages,
        "inferenceConfig": inference_config,
    }
    if payload.get("system"):
        kwargs["system"] = payload["system"]

    started = time.perf_counter()
    try:
        response = bedrock.converse(**kwargs)
    except Exception as exc:  # noqa: BLE001 - map AWS errors to HTTP
        logger.exception("Bedrock converse failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Bedrock invocation failed",
        ) from exc

    latency_ms = (time.perf_counter() - started) * 1000
    input_tokens, output_tokens = extract_usage(response)
    emit_usage(
        cloudwatch,
        settings.metrics_namespace,
        app_record["app_id"],
        model_alias,
        input_tokens,
        output_tokens,
        latency_ms,
    )

    body = {
        "app_id": app_record["app_id"],
        "model": model_alias,
        "output": response.get("output"),
        "stopReason": response.get("stopReason"),
        "usage": response.get("usage"),
    }
    return JSONResponse(content=_jsonable(body))


@app.post("/v1/infer")
async def infer(payload: dict[str, Any]) -> JSONResponse:
    """Experiment path. Tenant identity is injected by the load generator.

    Production traffic uses POST /v1/converse with SigV4-authenticated
    principals mapped through DynamoDB. Do not treat client-supplied
    tenant_id as a production auth mechanism.
    """
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Body must include tenant_id")

    tenant = get_tenant(tenants_table, tenant_id)
    prompt_class = payload.get("prompt_class", "medium")
    defaults = PROMPT_CLASSES.get(prompt_class, PROMPT_CLASSES["medium"])
    estimated_input = int(payload.get("input_tokens") or defaults["input_tokens"])
    max_tokens = int(payload.get("max_tokens") or defaults["max_tokens"])
    estimated_tokens = estimated_input + max_tokens
    prompt = payload.get("prompt")
    messages = payload.get("messages") or [
        {"role": "user", "content": [{"text": prompt if prompt else _default_prompt(prompt_class)}]}
    ]

    arrival_ts = time.time()
    decision, queue_ms = await _admit(tenant, estimated_tokens, arrival_ts)
    event = {
        "run_id": settings.run_id,
        "policy": policy.name,
        "tenant_id": tenant_id,
        "tier": tenant["tier"],
        "input_tokens": estimated_input,
        "output_tokens": 0,
        "arrival_ts": arrival_ts,
        "admit_ts": None,
        "first_token_ts": None,
        "finish_ts": None,
        "queue_ms": queue_ms,
        "ttft_ms": None,
        "e2e_ms": None,
        "decision": decision.action,
        "reason": decision.reason,
        "slo_met": False,
        "bedrock_429": False,
        "bedrock_5xx": False,
    }

    if decision.action != "ADMIT":
        counters.record_reject(tenant_id)
        event["finish_ts"] = time.time()
        event["e2e_ms"] = (event["finish_ts"] - arrival_ts) * 1000
        results.write(event)
        status_code = 429 if decision.action == "REJECT" else 503
        return JSONResponse(status_code=status_code, content=event)

    admit_ts = time.time()
    event["admit_ts"] = admit_ts
    counters.record_admit(
        tenant_id,
        estimated_tokens,
        tenant_tpm_limit=tenant["tpm_limit"],
        platform_tpm_budget=settings.platform_tpm_budget,
        use_buckets=USE_BUCKETS,
    )
    try:
        stream = converse_stream(
            bedrock,
            model_id=settings.experiment_model_id,
            messages=messages,
            max_tokens=max_tokens,
            start_ts=admit_ts,
            collect_text=bool(payload.get("include_output")),
        )
    finally:
        counters.release_concurrency(tenant_id)

    event.update(
        {
            "input_tokens": stream.input_tokens or estimated_input,
            "output_tokens": stream.output_tokens,
            "first_token_ts": stream.first_token_ts,
            "finish_ts": stream.finish_ts,
            "ttft_ms": stream.ttft_ms,
            "e2e_ms": stream.e2e_ms + queue_ms,
            "bedrock_429": stream.bedrock_429,
            "bedrock_5xx": stream.bedrock_5xx,
        }
    )
    ttft_for_slo = (stream.ttft_ms or stream.e2e_ms) + queue_ms
    event["slo_met"] = stream.ttft_ms is not None and ttft_for_slo <= tenant["ttft_slo_ms"]
    if not event["slo_met"]:
        counters.record_slo_violation(tenant_id)
    results.write(event)

    status_code = 200
    if stream.bedrock_429:
        status_code = 429
    elif stream.bedrock_5xx:
        status_code = 502
    body = {**event, "error": stream.error}
    if stream.text:
        body["output_text"] = stream.text
    return JSONResponse(status_code=status_code, content=_jsonable(body))


async def _admit(tenant: dict[str, Any], estimated_tokens: int, arrival_ts: float) -> tuple[Decision, float]:
    max_wait_ms = float(tenant["ttft_slo_ms"])
    queued = False
    try:
        while True:
            wait_ms = (time.time() - arrival_ts) * 1000
            snap = counters.snapshot(
                tenant["tenant_id"],
                tenant_tpm_limit=tenant["tpm_limit"],
                platform_tpm_budget=settings.platform_tpm_budget,
                use_buckets=USE_BUCKETS,
            )
            ctx = RequestContext(
                tenant_id=tenant["tenant_id"],
                tier=tenant["tier"],
                weight=tenant["weight"],
                estimated_tokens=estimated_tokens,
                wait_ms=wait_ms,
                ttft_slo_ms=tenant["ttft_slo_ms"],
                estimated_backend_ttft_ms=settings.estimated_backend_ttft_ms,
                tenant_tpm_used=int(snap["tenant_tpm"]),
                tenant_tpm_limit=tenant["tpm_limit"],
                tenant_rpm_used=int(snap["tenant_rpm"]),
                tenant_rpm_limit=tenant["rpm_limit"],
                tenant_concurrency=int(snap["tenant_concurrency"]),
                tenant_max_concurrency=tenant["max_concurrency"],
                platform_tpm_used=int(snap["platform_tpm"]),
                platform_tpm_budget=settings.platform_tpm_budget,
                tenant_bucket_tokens=float(snap["tenant_bucket"]),
                platform_bucket_tokens=float(snap["platform_bucket"]),
                weight_sum=settings.tenant_weight_sum,
            )
            decision = policy.decide(ctx)
            if decision.action == "ADMIT":
                return decision, wait_ms
            if decision.action == "REJECT" or wait_ms >= max_wait_ms:
                if wait_ms >= max_wait_ms and decision.action == "QUEUE":
                    return Decision("REJECT", "queue-timeout"), wait_ms
                return decision, wait_ms
            if not queued:
                counters.adjust_queue(1)
                queued = True
            await asyncio.sleep(settings.queue_poll_ms / 1000)
    finally:
        if queued:
            counters.adjust_queue(-1)


@lru_cache(maxsize=8)
def _default_prompt(prompt_class: str) -> str:
    seed = "Summarize the following enterprise operations note in one sentence. "
    repeats = {"short": 8, "medium": 70, "long": 280}.get(prompt_class, 70)
    return seed + ("The queue depth is rising and latency SLOs are at risk. " * repeats)


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))
