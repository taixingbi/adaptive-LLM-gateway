from generate_tenants import tenants
from traffic import PLATFORM_TPM_BUDGET, assign_traffic, burst_multiplier, offered_tpm, scale_to_budget


def test_skew_on_100_tenants() -> None:
    profiles = assign_traffic(tenants())
    ranked = sorted(profiles, key=lambda p: p["rpm"], reverse=True)
    total = sum(p["rpm"] for p in ranked)
    top = sum(p["rpm"] for p in ranked[:10]) / total
    mid = sum(p["rpm"] for p in ranked[10:40]) / total
    bot = sum(p["rpm"] for p in ranked[40:]) / total
    assert 0.40 <= top <= 0.50
    assert 0.25 <= mid <= 0.35
    assert 0.20 <= bot <= 0.30
    assert {p["tenant_id"] for p in profiles} == {t["tenant_id"] for t in tenants()}


def test_p1_uses_short_or_medium() -> None:
    profiles = assign_traffic(tenants())
    p1 = [p for p in profiles if p["tier"] == "P1"]
    assert p1
    assert all(p["prompt_class"] in {"short", "medium"} for p in p1)
    assert all(5 <= p["base_rpm"] <= 15 for p in p1)


def test_burst_schedule() -> None:
    phases = [
        {"start_s": 0, "end_s": 180, "burst": 1.0},
        {"start_s": 180, "end_s": 360, "burst": 10.0},
        {"start_s": 360, "end_s": 540, "burst": 1.0},
    ]
    assert burst_multiplier(10, phases) == 1.0
    assert burst_multiplier(200, phases) == 10.0
    assert burst_multiplier(400, phases) == 1.0


def test_tenant_tpm_fits_a_medium_request() -> None:
    medium = 2198
    by_tier = {t["tier"]: t["tpm_limit"] for t in tenants()}
    assert by_tier["P1"] > PLATFORM_TPM_BUDGET
    assert by_tier["P2"] > medium
    assert by_tier["P3"] > medium


def test_scale_to_budget_hits_platform_c() -> None:
    profiles = assign_traffic(tenants())
    scale_to_budget(profiles, prompt_class="medium")
    offered = offered_tpm(profiles, "medium")
    assert abs(offered - PLATFORM_TPM_BUDGET) / PLATFORM_TPM_BUDGET < 0.01