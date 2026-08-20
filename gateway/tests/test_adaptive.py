import time

from app.adaptive_capacity import AdaptiveCapacity
from app.admission.base import get_policy
from app.counters import MemoryCounters, _k
from tests.helpers import ctx


def test_adaptive_policy_registered() -> None:
    policy = get_policy("adaptive-slo")
    assert policy.name == "adaptive-slo"
    decision = policy.decide(ctx(platform_tpm_used=10000))
    assert decision.action == "ADMIT"
    assert decision.reason.startswith("adaptive-")


def test_adaptive_hard_shed_uses_injected_budget() -> None:
    """With raised C_hat, same platform_tpm_used no longer hard-sheds."""
    policy = get_policy("adaptive-slo")
    hard = policy.decide(ctx(platform_tpm_used=120000, platform_tpm_budget=100000))
    soft = policy.decide(ctx(platform_tpm_used=120000, platform_tpm_budget=200000))
    assert hard.action == "REJECT"
    assert soft.action == "ADMIT"


def test_aimd_increases_when_healthy() -> None:
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, alpha=0.2, beta=0.5, window_s=0.05, c_max=500000)
    assert ctl.current_budget() == 100000
    for _ in range(10):
        ctl.observe(admitted=True, slo_met=True, bedrock_429=False)
    time.sleep(0.06)
    budget = ctl.current_budget()
    assert budget > 100000


def test_aimd_decreases_on_429() -> None:
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, alpha=0.2, beta=0.5, window_s=0.05, c_min=10000)
    assert ctl.current_budget() == 100000
    ctl.observe(admitted=True, slo_met=True, bedrock_429=True)
    time.sleep(0.06)
    budget = ctl.current_budget()
    assert budget <= 50000


def test_aimd_grows_fast_under_healthy_rejects() -> None:
    """Policy rejects with no Bedrock 429 → multiplicative increase."""
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, alpha=0.2, beta=0.5, window_s=0.05, c_max=2000000)
    for _ in range(20):
        ctl.observe(admitted=False, slo_met=None, bedrock_429=False)
    time.sleep(0.06)
    assert ctl.current_budget() >= 120000


def test_seed_does_not_clobber_existing_capacity() -> None:
    store = MemoryCounters()
    AdaptiveCapacity(store, c0=100000, window_s=60.0)
    store.set_raw(_k("adaptive", "capacity"), "250000", ttl_s=60)
    store.set_raw(_k("adaptive", "last_action"), "increase", ttl_s=60)
    # Long window so current_budget() does not AIMD-step before we read.
    ctl2 = AdaptiveCapacity(store, c0=100000, window_s=60.0)
    assert int(store.get_raw(_k("adaptive", "capacity"))) == 250000
    assert ctl2.current_budget() == 250000
