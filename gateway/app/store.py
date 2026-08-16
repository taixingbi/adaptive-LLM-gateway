from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from fastapi import HTTPException, status

from app.rate_limit import minute_window, ttl_epoch


def get_app_by_principal(table, principal_arn: str) -> dict[str, Any]:
    response = table.query(
        IndexName="principal_arn-index",
        KeyConditionExpression=Key("principal_arn").eq(principal_arn),
        Limit=1,
    )
    items = response.get("Items") or []
    if not items:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Caller is not registered",
        )
    item = items[0]
    return {
        "app_id": item["app_id"],
        "account_id": item.get("account_id", ""),
        "team": item.get("team", ""),
        "allowed_models": sorted(item.get("allowed_models") or []),
        "rpm_limit": int(item.get("rpm_limit", 0)),
        "token_limit": int(item.get("token_limit", 0)),
        "principal_arn": item["principal_arn"],
    }


def consume_quota(table, app: dict[str, Any], token_estimate: int) -> None:
    window = minute_window()
    try:
        table.update_item(
            Key={"app_id": app["app_id"], "window": window},
            UpdateExpression=(
                "ADD request_count :one, token_count :tokens "
                "SET expires_at = if_not_exists(expires_at, :ttl)"
            ),
            ConditionExpression=(
                "(attribute_not_exists(request_count) OR request_count < :rpm) "
                "AND (attribute_not_exists(token_count) OR token_count < :tpm)"
            ),
            ExpressionAttributeValues={
                ":one": 1,
                ":tokens": token_estimate,
                ":rpm": app["rpm_limit"],
                ":tpm": app["token_limit"],
                ":ttl": ttl_epoch(),
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            ) from exc
        raise
