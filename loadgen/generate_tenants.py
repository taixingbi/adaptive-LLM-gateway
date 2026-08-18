#!/usr/bin/env python3
"""Generate 100 logical tenants. Not 100 AWS accounts."""

from __future__ import annotations

from pathlib import Path

TIERS = [
    # count, tier, ttft_slo_ms, weight, tpm, rpm, concurrency
    (10, "P1", 1000, 4, 6000, 100, 10),
    (60, "P2", 2000, 2, 2000, 40, 4),
    (30, "P3", 5000, 1, 1000, 20, 2),
]

# Must match gateway Settings.tenant_weight_sum. Reserved TPM = C * weight / WEIGHT_SUM.
WEIGHT_SUM = sum(count * weight for count, _, _, weight, _, _, _ in TIERS)


def tenants() -> list[dict]:
    items: list[dict] = []
    n = 1
    for count, tier, slo, weight, tpm, rpm, conc in TIERS:
        for _ in range(count):
            items.append(
                {
                    "tenant_id": f"tenant-{n:03d}",
                    "tier": tier,
                    "tpm_limit": tpm,
                    "rpm_limit": rpm,
                    "max_concurrency": conc,
                    "ttft_slo_ms": slo,
                    "e2e_slo_ms": slo * 4,
                    "weight": weight,
                }
            )
            n += 1
    return items


def to_yaml(items: list[dict]) -> str:
    lines = ["# 100 logical enterprise apps. Seed into DynamoDB with scripts/seed_tenants.py.", "tenants:"]
    for item in items:
        lines.append(f"  - tenant_id: {item['tenant_id']}")
        for key, value in item.items():
            if key == "tenant_id":
                continue
            lines.append(f"    {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    out = Path(__file__).with_name("tenants.yaml")
    out.write_text(to_yaml(tenants()), encoding="utf-8")
    print(f"wrote {out} ({len(tenants())} tenants)")


if __name__ == "__main__":
    main()
