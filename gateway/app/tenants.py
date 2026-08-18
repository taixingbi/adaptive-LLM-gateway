from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


DEFAULT_TENANT = {
    "tier": "P2",
    "tpm_limit": 2000,
    "rpm_limit": 60,
    "max_concurrency": 4,
    "ttft_slo_ms": 2000,
    "e2e_slo_ms": 8000,
    "weight": 2,
}

_CACHE: dict[str, dict[str, Any]] = {}


def get_tenant(table, tenant_id: str) -> dict[str, Any]:
    cached = _CACHE.get(tenant_id)
    if cached is not None:
        return cached
    response = table.get_item(Key={"tenant_id": tenant_id})
    item = response.get("Item")
    if not item:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown tenant '{tenant_id}'",
        )
    parsed = {
        "tenant_id": item["tenant_id"],
        "tier": item.get("tier", DEFAULT_TENANT["tier"]),
        "tpm_limit": int(item.get("tpm_limit", DEFAULT_TENANT["tpm_limit"])),
        "rpm_limit": int(item.get("rpm_limit", DEFAULT_TENANT["rpm_limit"])),
        "max_concurrency": int(item.get("max_concurrency", DEFAULT_TENANT["max_concurrency"])),
        "ttft_slo_ms": int(item.get("ttft_slo_ms", DEFAULT_TENANT["ttft_slo_ms"])),
        "e2e_slo_ms": int(item.get("e2e_slo_ms", DEFAULT_TENANT["e2e_slo_ms"])),
        "weight": int(item.get("weight", DEFAULT_TENANT["weight"])),
    }
    _CACHE[tenant_id] = parsed
    return parsed
