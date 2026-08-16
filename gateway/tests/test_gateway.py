from datetime import datetime, timezone

from app.auth import assert_model_allowed, caller_arn_from_headers, normalize_principal_arn
from app.models import extract_usage, load_model_map, resolve_profile
from app.rate_limit import minute_window
from fastapi import HTTPException


def test_minute_window_is_utc_minute() -> None:
    now = datetime(2026, 8, 16, 12, 34, 56, tzinfo=timezone.utc)
    assert minute_window(now) == "2026-08-16T12:34"


def test_normalize_assumed_role() -> None:
    assumed = "arn:aws:sts::123456789012:assumed-role/bedrock-platform-dev-app-app-002/session"
    assert (
        normalize_principal_arn(assumed)
        == "arn:aws:iam::123456789012:role/bedrock-platform-dev-app-app-002"
    )


def test_caller_arn_required() -> None:
    try:
        caller_arn_from_headers({}, "x-caller-arn")
        raise AssertionError("expected 401")
    except HTTPException as exc:
        assert exc.status_code == 401


def test_model_allowlist() -> None:
    app = {"app_id": "app-002", "allowed_models": ["nova-lite"]}
    assert_model_allowed(app, "nova-lite")
    try:
        assert_model_allowed(app, "llama")
        raise AssertionError("expected 403")
    except HTTPException as exc:
        assert exc.status_code == 403


def test_resolve_profile() -> None:
    mapping = load_model_map('{"nova-lite": "arn:aws:bedrock:us-east-1:123:inference-profile/x"}')
    assert resolve_profile(mapping, "nova-lite").endswith("/x")
    try:
        resolve_profile(mapping, "missing")
        raise AssertionError("expected 400")
    except HTTPException as exc:
        assert exc.status_code == 400


def test_extract_usage() -> None:
    assert extract_usage({"usage": {"inputTokens": 9, "outputTokens": 4}}) == (9, 4)
