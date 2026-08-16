import json
from typing import Any

from fastapi import HTTPException, status


def load_model_map(raw: str) -> dict[str, str]:
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("MODEL_MAP_JSON is not valid JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError("MODEL_MAP_JSON must be an object")
    return {str(k): str(v) for k, v in data.items()}


def resolve_profile(model_map: dict[str, str], alias: str) -> str:
    profile = model_map.get(alias)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown model alias '{alias}'",
        )
    return profile


def extract_usage(response: dict[str, Any]) -> tuple[int, int]:
    usage = response.get("usage") or {}
    return int(usage.get("inputTokens") or 0), int(usage.get("outputTokens") or 0)
