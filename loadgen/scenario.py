"""Load experiments/*.yaml into a Locust-ready config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from generate_tenants import tenants as all_tenants
from traffic import PLATFORM_TPM_BUDGET, assign_traffic, scale_to_budget


def load_scenario(path: Path, *, smoke: bool = False, load_pct: float | None = None) -> dict[str, Any]:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    tenant_n = int(spec.get("tenants", 100))
    duration_s = _duration(spec)
    if smoke:
        smoke_spec = spec.get("smoke") or {}
        tenant_n = int(smoke_spec.get("tenants", min(10, tenant_n)))
        duration_s = int(smoke_spec.get("duration_s", duration_s))
    tenants = all_tenants()[:tenant_n]
    profiles = assign_traffic(tenants, mix=spec.get("mix"))
    if spec.get("rpm"):
        current = sum(p["rpm"] for p in profiles)
        factor = float(spec["rpm"]) / max(current, 0.1)
        for profile in profiles:
            profile["rpm"] *= factor
    elif smoke and (spec.get("smoke") or {}).get("rpm"):
        mean = sum(p["rpm"] for p in profiles) / max(len(profiles), 1)
        factor = float(spec["smoke"]["rpm"]) / max(mean, 0.1)
        for profile in profiles:
            profile["rpm"] *= factor
    else:
        load_frac = 1.0 if load_pct is None else load_pct / 100.0
        scale_to_budget(
            profiles,
            budget=int(spec.get("platform_tpm_budget", PLATFORM_TPM_BUDGET)),
            load_frac=load_frac,
            prompt_class=spec.get("prompt_class"),
        )
    packed = _pack(spec, profiles, duration_s)
    if smoke and packed["phases"]:
        width = packed["duration_s"] / max(len(packed["phases"]), 1)
        for idx, phase in enumerate(packed["phases"]):
            phase["start_s"] = int(idx * width)
            phase["end_s"] = int((idx + 1) * width)
    return packed


def _duration(spec: dict[str, Any]) -> int:
    if spec.get("duration_s"):
        return int(spec["duration_s"])
    phases = spec.get("phases") or []
    if phases and "minutes" in (phases[0] or {}):
        return int(max(p["minutes"][1] for p in phases) * 60)
    if phases:
        return int(spec.get("phase_duration_s", 180)) * len(phases)
    return 300


def _pack(spec: dict[str, Any], profiles: list[dict], duration_s: int) -> dict[str, Any]:
    phases = []
    for phase in spec.get("phases") or []:
        if "minutes" in phase:
            start_m, end_m = phase["minutes"]
            burst = float(str(phase.get("burst", "1x")).rstrip("x"))
            phases.append(
                {
                    "start_s": int(start_m * 60),
                    "end_s": int(end_m * 60),
                    "burst": burst,
                    "name": phase.get("name"),
                }
            )
        else:
            phases.append(phase)
    return {
        "name": spec["name"],
        "scenario": spec.get("scenario", spec["name"]),
        "victim": spec.get("victim"),
        "policies": spec.get("policies") or ["none"],
        "repetitions": int(spec.get("repetitions", 1)),
        "plot": spec.get("plot") or {},
        "prompt_class": spec.get("prompt_class"),
        "token_phases": [p for p in (spec.get("phases") or []) if "prompt_class" in p],
        "phase_duration_s": int(spec.get("phase_duration_s", 180)),
        "profiles": profiles,
        "phases": phases,
        "duration_s": duration_s,
        "exclude_victim": bool((spec.get("plot") or {}).get("exclude_victim")),
        "load_pcts": spec.get("load_pct") or [None],
    }
