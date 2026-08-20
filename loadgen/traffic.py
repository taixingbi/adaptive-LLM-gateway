"""Deterministic heterogeneous tenant traffic for paper experiments.

P1: 5–15 RPM, short/medium
P2: 5–20 RPM, short/medium/long
P3: 1–10 RPM, medium/long

Then skew so the busiest 10% carry ~45% of requests, the next 30% carry ~30%,
and the rest carry ~25%. Repeatable via tenant_id seed.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import yaml

TIER_RPM = {"P1": (5.0, 15.0), "P2": (5.0, 20.0), "P3": (1.0, 10.0)}
TIER_PROMPTS = {
    "P1": ("short", "medium"),
    "P2": ("short", "medium", "long"),
    "P3": ("medium", "long"),
}
SKEW = ((0.10, 0.45), (0.30, 0.30), (0.60, 0.25))
PLATFORM_TPM_BUDGET = 100_000


def _prompt_tokens() -> dict[str, int]:
    manifest = yaml.safe_load((Path(__file__).parent / "prompts" / "manifest.yaml").read_text(encoding="utf-8"))
    return {
        name: int(spec["input_tokens"]) + int(spec["max_tokens"])
        for name, spec in manifest["prompts"].items()
    }


PROMPT_TOKENS = _prompt_tokens()


def assign_traffic(
    tenants: list[dict[str, Any]],
    *,
    seed: int = 7,
    load_scale: float = 1.0,
    mix: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    profiles = [_base_profile(tenant, seed, mix) for tenant in tenants]
    _apply_skew(profiles)
    if load_scale != 1.0:
        for profile in profiles:
            profile["rpm"] *= load_scale
    return profiles


def _base_profile(tenant: dict[str, Any], seed: int, mix: dict[str, Any] | None) -> dict[str, Any]:
    rng = random.Random(f"{seed}:{tenant['tenant_id']}")
    lo, hi = TIER_RPM[tenant["tier"]]
    prompts = TIER_PROMPTS[tenant["tier"]]
    if mix:
        if tenant["tier"] == "P1":
            lo, hi = 1.0, 4.0
        elif tenant["tier"] == "P3":
            lo, hi = 10.0, 20.0
    return {
        **tenant,
        "base_rpm": rng.uniform(lo, hi),
        "prompt_class": rng.choice(prompts),
        "rpm": 0.0,
    }


def _apply_skew(profiles: list[dict[str, Any]]) -> None:
    if len(profiles) < 10:
        for profile in profiles:
            profile["rpm"] = profile["base_rpm"]
        return
    ranked = sorted(profiles, key=lambda p: p["base_rpm"], reverse=True)
    n = len(ranked)
    total = sum(p["base_rpm"] for p in ranked) or 1.0
    start = 0
    for frac, share in SKEW:
        size = max(0, round(n * frac))
        if start + size > n:
            size = n - start
        group = ranked[start : start + size]
        start += size
        if not group:
            continue
        gtot = sum(p["base_rpm"] for p in group) or 1.0
        target = total * share
        for profile in group:
            profile["rpm"] = profile["base_rpm"] * (target / gtot)
    leftover = ranked[start:]
    if leftover:
        rest = sum(p["rpm"] for p in ranked[:start])
        target = max(total - rest, total * 0.05)
        gtot = sum(p["base_rpm"] for p in leftover) or 1.0
        for profile in leftover:
            profile["rpm"] = profile["base_rpm"] * (target / gtot)


def offered_tpm(profiles: list[dict[str, Any]], prompt_class: str | None = None) -> float:
    total = 0.0
    for profile in profiles:
        cls = prompt_class or profile.get("prompt_class") or "medium"
        total += float(profile["rpm"]) * PROMPT_TOKENS.get(cls, PROMPT_TOKENS["medium"])
    return total


def scale_to_budget(
    profiles: list[dict[str, Any]],
    *,
    budget: int = PLATFORM_TPM_BUDGET,
    load_frac: float = 1.0,
    prompt_class: str | None = None,
) -> None:
    """Scale RPM so offered TPM ≈ load_frac × C. Burst phases apply on top."""
    current = offered_tpm(profiles, prompt_class)
    target = budget * load_frac
    if current <= 0 or target <= 0:
        return
    factor = target / current
    for profile in profiles:
        profile["rpm"] *= factor


def burst_multiplier(elapsed_s: float, phases: list[dict]) -> float:
    for phase in phases:
        if phase["start_s"] <= elapsed_s < phase["end_s"]:
            return phase["burst"]
    return phases[-1]["burst"] if phases else 1.0
