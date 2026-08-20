#!/usr/bin/env python3
"""Paper plots from gateway JSONL. CloudWatch is for live dashboards only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from metrics import load_events, summarize  # noqa: E402
from runs import plot_triple  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("analysis/result_paper"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    by_policy: dict[str, list] = {}
    for event in load_events(args.results_dir):
        by_policy.setdefault(event.get("policy", "unknown"), []).append(event)

    names = sorted(by_policy)
    stats = [summarize(by_policy[name]) for name in names]
    plot_triple(
        args.out / "policy_compare.png",
        names,
        goodput=[s["effective_slo_goodput"] for s in stats],
        p99=[s["p99_ttft_ms"] or 0 for s in stats],
        throttle=[s["throttle_rate"] for s in stats],
        title="Policy comparison (JSONL)",
    )
    print(f"wrote {args.out / 'policy_compare.png'}")


if __name__ == "__main__":
    main()
