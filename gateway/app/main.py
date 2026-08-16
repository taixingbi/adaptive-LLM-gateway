import json
import logging
import time
from typing import Any

import boto3
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.auth import assert_model_allowed, caller_arn_from_headers
from app.config import get_settings
from app.models import extract_usage, load_model_map, resolve_profile
from app.store import consume_quota, get_app_by_principal
from app.usage import emit_usage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="bedrock-platform LLM Gateway", version="0.1.0")
settings = get_settings()
model_map = load_model_map(settings.model_map_json)

session = boto3.Session(region_name=settings.aws_region)
dynamodb = session.resource("dynamodb")
apps_table = dynamodb.Table(settings.apps_table)
rate_table = dynamodb.Table(settings.rate_limits_table)
bedrock = session.client("bedrock-runtime")
cloudwatch = session.client("cloudwatch")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    return JSONResponse(content=json.loads(json.dumps(body, default=str)))
