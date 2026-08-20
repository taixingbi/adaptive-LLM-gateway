from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class RequestContext:
    tenant_id: str
    tier: str
    weight: int
    estimated_tokens: int
    wait_ms: float
    ttft_slo_ms: int
    estimated_backend_ttft_ms: float
    tenant_tpm_used: int
    tenant_tpm_limit: int
    tenant_rpm_used: int
    tenant_rpm_limit: int
    tenant_concurrency: int
    tenant_max_concurrency: int
    platform_tpm_used: int
    platform_tpm_budget: int
    tenant_bucket_tokens: float = 0.0
    platform_bucket_tokens: float = 0.0
    weight_sum: int = 190

    @property
    def platform_pressure(self) -> float:
        if self.platform_tpm_budget <= 0:
            return 1.0
        return self.platform_tpm_used / self.platform_tpm_budget

    @property
    def remaining_slack_ms(self) -> float:
        return self.ttft_slo_ms - self.wait_ms - self.estimated_backend_ttft_ms

    @property
    def reserved_tpm(self) -> float:
        if self.weight_sum <= 0:
            return 0.0
        return self.platform_tpm_budget * self.weight / self.weight_sum


@dataclass
class Decision:
    action: str  # ADMIT | QUEUE | REJECT
    reason: str


class AdmissionPolicy(Protocol):
    name: str

    def decide(self, ctx: RequestContext) -> Decision: ...


_POLICIES: dict[str, AdmissionPolicy] | None = None


def get_policy(name: str) -> AdmissionPolicy:
    global _POLICIES
    if _POLICIES is None:
        from app.admission import adaptive_slo, none, priority, rpm, slo_aware, token_bucket, tpm

        _POLICIES = {
            "none": none.NonePolicy(),
            "rpm": rpm.RpmPolicy(),
            "rpm-fixed": rpm.RpmPolicy(),
            "tpm": tpm.TpmPolicy(),
            "tpm-fixed": tpm.TpmPolicy(),
            "token-bucket": token_bucket.TokenBucketPolicy(),
            "priority": priority.PriorityPolicy(),
            "slo-aware": slo_aware.SloAwarePolicy(),
            "slo_aware": slo_aware.SloAwarePolicy(),
            "adaptive-slo": adaptive_slo.AdaptiveSloAwarePolicy(),
            "adaptive_slo": adaptive_slo.AdaptiveSloAwarePolicy(),
        }
    try:
        return _POLICIES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown admission policy '{name}'. Choose: {sorted(_POLICIES)}") from exc
