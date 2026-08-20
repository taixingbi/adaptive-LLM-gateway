from app.adaptive_capacity import AdaptiveCapacity
from app.admission.base import RequestContext, get_policy
from app.counters import MemoryCounters


def _ctx(**overrides) -> RequestContext:
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


def test_adaptive_policy_registered() -> None:
    policy = get_policy("adaptive-slo")
    assert policy.name == "adaptive-slo"
    decision = policy.decide(_ctx(platform_tpm_used=10000))
    assert decision.action == "ADMIT"
    assert decision.reason.startswith("adaptive-")


def test_adaptive_hard_shed_uses_injected_budget() -> None:
    """With raised C_hat, same platform_tpm_used no longer hard-sheds."""
    policy = get_policy("adaptive-slo")
    hard = policy.decide(_ctx(platform_tpm_used=120000, platform_tpm_budget=100000))
    soft = policy.decide(_ctx(platform_tpm_used=120000, platform_tpm_budget=200000))
    assert hard.action == "REJECT"
    assert soft.action == "ADMIT"


def test_aimd_increases_when_healthy() -> None:
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, alpha=0.2, beta=0.5, window_s=0.05, c_max=500000)
    assert ctl.current_budget() == 100000
    for _ in range(10):
        ctl.observe(admitted=True, slo_met=True, bedrock_429=False)
    import time

    time.sleep(0.06)
    budget = ctl.current_budget()
    assert budget > 100000


def test_aimd_decreases_on_429() -> None:
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, alpha=0.2, beta=0.5, window_s=0.05, c_min=10000)
    assert ctl.current_budget() == 100000
    ctl.observe(admitted=True, slo_met=True, bedrock_429=True)
    import time

    time.sleep(0.06)
    budget = ctl.current_budget()
    assert budget <= 50000
