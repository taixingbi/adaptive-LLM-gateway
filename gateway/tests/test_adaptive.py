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


def _tick(ctl: AdaptiveCapacity) -> int:
    ctl._local_last_update = 0.0
    ctl._store.set_raw(ctl._updated_key, "0", ttl_s=60)
    return ctl.current_budget()


def test_aimd_increases_when_healthy() -> None:
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, alpha=0.2, beta=0.5, window_s=0.05, c_max=500000)
    assert ctl.current_budget() == 100000
    for _ in range(10):
        ctl.observe(admitted=True, slo_met=True, bedrock_429=False)
    assert _tick(ctl) > 100000


def test_aimd_decreases_on_429() -> None:
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, alpha=0.2, beta=0.5, window_s=0.05, c_min=10000)
    store.set_raw(_k("adaptive", "capacity"), "200000", ttl_s=60)
    ctl.observe(admitted=True, slo_met=True, bedrock_429=True)
    assert _tick(ctl) <= 100000


def test_aimd_grows_fast_under_healthy_rejects() -> None:
    """Policy rejects with no Bedrock 429 → multiplicative increase."""
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, alpha=0.2, beta=0.5, window_s=0.05, c_max=2000000)
    for _ in range(20):
        ctl.observe(admitted=False, slo_met=None, bedrock_429=False)
    assert _tick(ctl) >= 120000


def test_slo_fail_without_429_does_not_shrink() -> None:
    """Local SLO misses are not a global health signal."""
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, alpha=0.2, beta=0.5, window_s=0.05, c_min=10000, c_max=2000000)
    store.set_raw(_k("adaptive", "capacity"), "200000", ttl_s=60)
    for _ in range(10):
        ctl.observe(admitted=True, slo_met=False, bedrock_429=False)
    assert _tick(ctl) >= 200000


def test_aimd_decreases_on_5xx() -> None:
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, alpha=0.2, beta=0.5, window_s=0.05, c_min=10000)
    store.set_raw(_k("adaptive", "capacity"), "200000", ttl_s=60)
    ctl.observe(admitted=True, slo_met=True, bedrock_429=False, bedrock_5xx=True)
    assert _tick(ctl) <= 100000


def test_reset_returns_to_c0() -> None:
    store = MemoryCounters()
    ctl = AdaptiveCapacity(store, c0=100000, window_s=60.0)
    store.set_raw(_k("adaptive", "capacity"), "2000000", ttl_s=60)
    store.set_raw(_k("adaptive", "last_action"), "increase-demand", ttl_s=60)
    assert ctl.reset() == 100000
    assert int(store.get_raw(_k("adaptive", "capacity"))) == 100000
    assert ctl.current_budget() == 100000
    assert store.get_raw(_k("adaptive", "last_action")) == "reset"


def test_seed_does_not_clobber_existing_capacity() -> None:
    store = MemoryCounters()
    AdaptiveCapacity(store, c0=100000, window_s=60.0)
    store.set_raw(_k("adaptive", "capacity"), "250000", ttl_s=60)
    store.set_raw(_k("adaptive", "last_action"), "increase", ttl_s=60)
    # Long window so current_budget() does not AIMD-step before we read.
    ctl2 = AdaptiveCapacity(store, c0=100000, window_s=60.0)
    assert int(store.get_raw(_k("adaptive", "capacity"))) == 250000
    assert ctl2.current_budget() == 250000
