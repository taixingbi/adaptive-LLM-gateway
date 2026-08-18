#!/usr/bin/env python3
"""Paper plots from gateway JSONL. CloudWatch is for live dashboards only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from metrics import load_events, summarize


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("analysis/out"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    by_policy: dict[str, list] = {}
    for event in load_events(args.results_dir):
        by_policy.setdefault(event.get("policy", "unknown"), []).append(event)

    names = sorted(by_policy)
    slo = [summarize(by_policy[name])["slo_attainment"] * 100 for name in names]
    p99 = [summarize(by_policy[name])["p99_ttft_ms"] or 0 for name in names]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].bar(names, slo)
    axes[0].set_ylabel("SLO attainment (%)")
    axes[0].set_ylim(0, 100)
    axes[1].bar(names, p99)
    axes[1].set_ylabel("P99 TTFT (ms)")
    fig.tight_layout()
    fig.savefig(args.out / "policy_compare.png", dpi=150)
    print(f"wrote {args.out / 'policy_compare.png'}")


if __name__ == "__main__":
    main()
