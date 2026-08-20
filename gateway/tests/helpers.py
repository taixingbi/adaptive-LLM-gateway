from app.admission.base import RequestContext


def ctx(**overrides) -> RequestContext:
    base = dict(
        tenant_id="tenant-007",
        tier="P2",
        weight=2,
        estimated_tokens=500,
        wait_ms=0,
        ttft_slo_ms=2000,
        estimated_backend_ttft_ms=400,
        tenant_tpm_used=0,
        tenant_tpm_limit=10000,
        tenant_rpm_used=0,
        tenant_rpm_limit=100,
        tenant_concurrency=0,
        tenant_max_concurrency=10,
        platform_tpm_used=0,
        platform_tpm_budget=100000,
    )
    base.update(overrides)
    return RequestContext(**base)
