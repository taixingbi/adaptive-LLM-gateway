from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def load_events(path: Path) -> list[dict]:
    events = []
    if path.is_file():
        files = [path]
    else:
        files = sorted(path.rglob("*.jsonl"))
    for file in files:
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def summarize(events: list[dict], exclude_tenants: set[str] | None = None) -> dict:
    rows = events if not exclude_tenants else [e for e in events if e.get("tenant_id") not in exclude_tenants]
    n = len(rows) or 1
    admitted = [e for e in rows if e.get("decision") == "ADMIT"]
    ttfts = sorted(e["ttft_ms"] for e in admitted if e.get("ttft_ms") is not None)
    slo = sum(1 for e in admitted if e.get("slo_met")) / max(len(admitted), 1)
    return {
        "requests": len(rows),
        "admit_rate": len(admitted) / n,
        "reject_rate": sum(1 for e in rows if e.get("decision") == "REJECT") / n,
        "slo_attainment": slo,
        "p50_ttft_ms": _pct(ttfts, 0.50),
        "p99_ttft_ms": _pct(ttfts, 0.99),
        "bedrock_429_rate": sum(1 for e in rows if e.get("bedrock_429")) / n,
        "bedrock_5xx_rate": sum(1 for e in rows if e.get("bedrock_5xx")) / n,
        "throttle_rate": sum(1 for e in rows if e.get("decision") == "REJECT" or e.get("bedrock_429")) / n,
        "by_tier": _by_tier(rows),
    }


def _by_tier(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list] = defaultdict(list)
    for event in rows:
        grouped[event.get("tier", "?")].append(event)
    return {tier: summarize_simple(items) for tier, items in grouped.items()}


def summarize_simple(rows: list[dict]) -> dict:
    admitted = [e for e in rows if e.get("decision") == "ADMIT"]
    return {
        "n": len(rows),
        "slo_attainment": sum(1 for e in admitted if e.get("slo_met")) / max(len(admitted), 1),
        "admit_rate": len(admitted) / max(len(rows), 1),
    }


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    idx = min(len(values) - 1, max(0, int(q * (len(values) - 1))))
    return values[idx]
