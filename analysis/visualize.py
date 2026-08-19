#!/usr/bin/env python3
"""Simple policy-level visualization from summary.json runs.

Input runs typically live under `analysis/archive/*/summary.json` (raw run folders),
while the generated paper artifacts go to `analysis/result_paper/`.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from statistics import mean, pstdev

import matplotlib.pyplot as plt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("analysis/archive"))
    parser.add_argument("--out", type=Path, default=Path("analysis/result_paper"))
    parser.add_argument("--scenario", default="noisy_neighbor")
    parser.add_argument("--title", default="Policy comparison")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    runs = _load_runs(args.input, args.scenario)
    if not runs:
        raise SystemExit(f"no summary.json found for scenario '{args.scenario}' in {args.input}")

    stats = _aggregate(runs)
    _write_csv(args.out / f"{args.scenario}_policy_summary.csv", stats)
    chart = args.out / f"{args.scenario}_policy_summary.png"
    _plot(chart, stats, args.title)
    print(f"wrote {chart}")


def _load_runs(out_dir: Path, scenario: str) -> list[dict]:
    pattern = re.compile(rf"{re.escape(scenario)}-([a-z\-]+)-r(\d+)-")
    rows: list[dict] = []
    for file in out_dir.glob(f"{scenario}-*/summary.json"):
        match = pattern.match(file.parent.name)
        if not match:
            continue
        policy = match.group(1)
        rep = int(match.group(2))
        summary = json.loads(file.read_text(encoding="utf-8"))
        rows.append({"policy": policy, "rep": rep, "summary": summary, "run": file.parent.name})
    return rows


def _aggregate(rows: list[dict]) -> list[dict]:
    by_policy: dict[str, list[dict]] = {}
    for row in rows:
        by_policy.setdefault(row["policy"], []).append(row["summary"])

    metrics = ["admit_rate", "slo_attainment", "p99_ttft_ms", "throttle_rate"]
    out: list[dict] = []
    for policy in sorted(by_policy):
        values = by_policy[policy]
        agg = {"policy": policy, "repetitions": len(values)}
        for metric in metrics:
            col = [v[metric] for v in values if v.get(metric) is not None]
            agg[f"{metric}_mean"] = mean(col)
            agg[f"{metric}_std"] = pstdev(col) if len(col) > 1 else 0.0
        out.append(agg)
    return out


def _write_csv(path: Path, rows: list[dict]) -> None:
    header = [
        "policy",
        "repetitions",
        "admit_rate_mean",
        "admit_rate_std",
        "slo_attainment_mean",
        "slo_attainment_std",
        "p99_ttft_ms_mean",
        "p99_ttft_ms_std",
        "throttle_rate_mean",
        "throttle_rate_std",
    ]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(row[h]) for h in header))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _plot(path: Path, rows: list[dict], title: str) -> None:
    names = [r["policy"] for r in rows]
    slo_mean = [100 * r["slo_attainment_mean"] for r in rows]
    slo_std = [100 * r["slo_attainment_std"] for r in rows]
    p99_mean = [r["p99_ttft_ms_mean"] for r in rows]
    p99_std = [r["p99_ttft_ms_std"] for r in rows]
    thr_mean = [100 * r["throttle_rate_mean"] for r in rows]
    thr_std = [100 * r["throttle_rate_std"] for r in rows]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    fig.suptitle(title)

    axes[0].bar(names, slo_mean, yerr=slo_std, capsize=3)
    axes[0].set_ylabel("SLO attainment (%)")
    axes[0].set_ylim(0, 100)
    axes[0].tick_params(axis="x", rotation=30)

    axes[1].bar(names, p99_mean, yerr=p99_std, capsize=3)
    axes[1].set_ylabel("P99 TTFT (ms)")
    axes[1].tick_params(axis="x", rotation=30)

    axes[2].bar(names, thr_mean, yerr=thr_std, capsize=3)
    axes[2].set_ylabel("Throttle rate (%)")
    axes[2].tick_params(axis="x", rotation=30)

    fig.tight_layout()
    fig.savefig(path, dpi=160)


if __name__ == "__main__":
    main()
