from app.admission.base import RequestContext, get_policy


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


def test_none_always_admits() -> None:
    decision = get_policy("none").decide(_ctx(tenant_rpm_used=10_000, platform_tpm_used=10**9))
    assert decision.action == "ADMIT"


def test_rpm_rejects_over_limit() -> None:
    policy = get_policy("rpm")
    assert policy.decide(_ctx(tenant_rpm_used=99)).action == "ADMIT"
    assert policy.decide(_ctx(tenant_rpm_used=100)).action == "REJECT"


def test_tpm_queues_when_request_would_exceed_quota() -> None:
    policy = get_policy("tpm")
    admit = policy.decide(_ctx(tenant_tpm_used=8000, estimated_tokens=500))
    queue = policy.decide(_ctx(tenant_tpm_used=8000, estimated_tokens=4000))
    assert admit.action == "ADMIT"
    assert queue.action == "QUEUE"
    assert queue.reason == "tenant-tpm-exceeded"


def test_priority_protects_p1_under_pressure() -> None:
    policy = get_policy("priority")
    p1 = policy.decide(_ctx(tier="P1", platform_tpm_used=96000))
    p3 = policy.decide(_ctx(tier="P3", platform_tpm_used=96000))
    assert p1.action == "ADMIT"
    assert p3.action == "REJECT"


def test_slo_aware_admits_tight_slack() -> None:
    policy = get_policy("slo-aware")
    tight = policy.decide(
        _ctx(
            tier="P2",
            platform_tpm_used=90000,
            wait_ms=1500,
            ttft_slo_ms=2000,
            estimated_backend_ttft_ms=400,
        )
    )
    slack = policy.decide(
        _ctx(
            tier="P2",
            platform_tpm_used=90000,
            wait_ms=100,
            ttft_slo_ms=5000,
            estimated_backend_ttft_ms=400,
        )
    )
    assert tight.action == "ADMIT"
    assert slack.action == "QUEUE"


def test_slo_aware_low_pressure_admits() -> None:
    decision = get_policy("slo-aware").decide(_ctx(platform_tpm_used=10000))
    assert decision.action == "ADMIT"
    assert decision.reason == "slo-low-pressure"


def test_slo_aware_p1_does_not_break_hard_ceiling() -> None:
    policy = get_policy("slo-aware")
    over_reserved = policy.decide(
        _ctx(
            tier="P1",
            weight=4,
            platform_tpm_used=105000,
            tenant_tpm_used=5000,
            estimated_tokens=500,
        )
    )
    hard = policy.decide(_ctx(tier="P1", platform_tpm_used=110000))
    reserved = policy.decide(
        _ctx(
            tier="P1",
            weight=4,
            platform_tpm_used=105000,
            tenant_tpm_used=0,
            estimated_tokens=500,
        )
    )
    assert over_reserved.action == "QUEUE"
    assert over_reserved.reason == "slo-over-capacity"
    assert hard.action == "REJECT"
    assert hard.reason == "slo-hard-shed"
    assert reserved.action == "ADMIT"
    assert reserved.reason == "slo-reserved"


def test_token_bucket_queues_when_empty() -> None:
    policy = get_policy("token-bucket")
    ok = policy.decide(_ctx(tenant_bucket_tokens=800, platform_bucket_tokens=5000, estimated_tokens=500))
    empty = policy.decide(_ctx(tenant_bucket_tokens=100, platform_bucket_tokens=5000, estimated_tokens=500))
    assert ok.action == "ADMIT"
    assert empty.action == "QUEUE"
    assert get_policy("tpm-fixed").name == "tpm"
    assert get_policy("rpm-fixed").name == "rpm"
