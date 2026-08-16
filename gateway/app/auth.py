from typing import Any

from fastapi import HTTPException, status


def normalize_principal_arn(arn: str) -> str:
    """Map STS assumed-role session ARNs to the IAM role ARN stored in DynamoDB."""
    if ":assumed-role/" not in arn:
        return arn
    parts = arn.split(":")
    account = parts[4]
    role_name = parts[5].split("/")[1]
    return f"arn:aws:iam::{account}:role/{role_name}"


def caller_arn_from_headers(headers: dict[str, str], header_name: str) -> str:
    value = headers.get(header_name) or headers.get(header_name.title())
    if not value or value == "-":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing caller identity. Invoke the HTTP API with IAM SigV4.",
        )
    return normalize_principal_arn(value.strip())


def assert_model_allowed(app: dict[str, Any], model: str) -> None:
    allowed = app.get("allowed_models") or []
    if model not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{model}' is not allowed for app {app.get('app_id')}",
        )
