import logging
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


def emit_usage(
    cloudwatch,
    namespace: str,
    app_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
) -> None:
    logger.info(
        "usage app_id=%s model=%s input_tokens=%s output_tokens=%s latency_ms=%.1f",
        app_id,
        model,
        input_tokens,
        output_tokens,
        latency_ms,
    )
    try:
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                _metric("Invocations", 1, "Count", app_id, model),
                _metric("InputTokens", input_tokens, "Count", app_id, model),
                _metric("OutputTokens", output_tokens, "Count", app_id, model),
                _metric("LatencyMs", latency_ms, "Milliseconds", app_id, model),
            ],
        )
    except (BotoCoreError, ClientError):
        logger.exception("Failed to emit CloudWatch metrics")


def _metric(name: str, value: float, unit: str, app_id: str, model: str) -> dict[str, Any]:
    return {
        "MetricName": name,
        "Value": value,
        "Unit": unit,
        "Dimensions": [
            {"Name": "AppId", "Value": app_id},
            {"Name": "Model", "Value": model},
        ],
    }
