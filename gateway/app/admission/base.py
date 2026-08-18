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

    @property
    def platform_pressure(self) -> float:
        if self.platform_tpm_budget <= 0:
            return 1.0
        return self.platform_tpm_used / self.platform_tpm_budget

    @property
    def remaining_slack_ms(self) -> float:
        return self.ttft_slo_ms - self.wait_ms - self.estimated_backend_ttft_ms


@dataclass
class Decision:
    action: str  # ADMIT | QUEUE | REJECT
    reason: str


class AdmissionPolicy(Protocol):
    name: str

    def decide(self, ctx: RequestContext) -> Decision: ...


def get_policy(name: str) -> AdmissionPolicy:
    from app.admission import none, priority, rpm, slo_aware, tpm

    policies = {
        "none": none.NonePolicy(),
        "rpm": rpm.RpmPolicy(),
        "tpm": tpm.TpmPolicy(),
        "priority": priority.PriorityPolicy(),
        "slo-aware": slo_aware.SloAwarePolicy(),
        "slo_aware": slo_aware.SloAwarePolicy(),
    }
    if name not in policies:
        raise ValueError(f"Unknown admission policy '{name}'. Choose: {sorted(policies)}")
    return policies[name]
