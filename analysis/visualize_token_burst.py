#!/usr/bin/env python3
"""Aggregate token_burst runs with frozen selection and burst-phase breakdown."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from statistics import mean, pstdev

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from metrics import load_events, summarize


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("analysis/out"))
    parser.add_argument("--out", type=Path, default=Path("analysis/result_paper"))
    parser.add_argument("--scenario", default="token_burst")
    parser.add_argument("--rep-min", type=int, default=1)
    parser.add_argument("--rep-max", type=int, default=5)
    parser.add_argument("--burst-start-s", type=int, default=180)
    parser.add_argument("--burst-end-s", type=int, default=360)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    selected = _select_latest(_load_runs(args.input, args.scenario), args.rep_min, args.rep_max)
    if not selected:
        raise SystemExit(f"no runs found for scenario={args.scenario} in {args.input}")

    full_stats = _aggregate_full(selected)
    burst_stats = _aggregate_burst(selected, args.burst_start_s, args.burst_end_s)

    stem = args.scenario
    _write_csv(args.out / f"{stem}_policy_summary.csv", full_stats)
    _write_md(
        args.out / f"{stem}_all_policies_summary.md",
        full_stats,
        selected,
        args.rep_min,
        args.rep_max,
        title="Token Burst All-Policies Summary (full run)",
    )
    _write_md(
        args.out / f"{stem}_burst_phase_summary.md",
        burst_stats,
        selected,
        args.rep_min,
        args.rep_max,
        title="Token Burst Burst-Phase Summary (seconds 180–360)",
        burst_window=(args.burst_start_s, args.burst_end_s),
    )
    _plot(args.out / f"{stem}_policy_summary.png", burst_stats, "Token burst (burst phase)")
    print(f"wrote {args.out / f'{stem}_policy_summary.png'}")


def _load_runs(root: Path, scenario: str) -> list[dict]:
    pattern = re.compile(rf"{re.escape(scenario)}-([a-z\-]+)-r(\d+)-")
    rows: list[dict] = []
    for file in root.glob(f"{scenario}-*/summary.json"):
        match = pattern.match(file.parent.name)
        if not match:
            continue
        rows.append(
            {
                "policy": match.group(1),
                "rep": int(match.group(2)),
                "run": file.parent.name,
                "run_dir": file.parent,
                "summary": json.loads(file.read_text(encoding="utf-8")),
            }
        )
    return rows


def _select_latest(rows: list[dict], rep_min: int, rep_max: int) -> list[dict]:
    latest: dict[tuple[str, int], dict] = {}
    for row in rows:
        if row["rep"] < rep_min or row["rep"] > rep_max:
            continue
        key = (row["policy"], row["rep"])
        prev = latest.get(key)
        if prev is None or row["run"] > prev["run"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda r: (r["policy"], r["rep"]))


def _aggregate_full(rows: list[dict]) -> list[dict]:
    by_policy: dict[str, list[dict]] = {}
    for row in rows:
        by_policy.setdefault(row["policy"], []).append(row["summary"])
    return [_stats(policy, vals) for policy, vals in sorted(by_policy.items())]


def _aggregate_burst(rows: list[dict], start_s: int, end_s: int) -> list[dict]:
    by_policy: dict[str, list[dict]] = {}
    for row in rows:
        events = load_events(row["run_dir"])
        if not events:
            continue
        t0 = min(e["arrival_ts"] for e in events)
        burst = [e for e in events if start_s <= e["arrival_ts"] - t0 < end_s]
        by_policy.setdefault(row["policy"], []).append(summarize(burst))
    return [_stats(policy, vals) for policy, vals in sorted(by_policy.items())]


def _stats(policy: str, vals: list[dict]) -> dict:
    cond = [v.get("conditional_slo_attainment", v.get("slo_attainment")) for v in vals]
    goodput = [
        v.get("effective_slo_goodput", v.get("slo_goodput", v.get("admit_rate", 0.0) * v.get("slo_attainment", 0.0)))
        for v in vals
    ]
    admit = [v["admit_rate"] for v in vals]
    throttle = [v["throttle_rate"] for v in vals]
    p99 = [v["p99_ttft_ms"] for v in vals if v.get("p99_ttft_ms") is not None]
    p95 = [v["p95_ttft_ms"] for v in vals if v.get("p95_ttft_ms") is not None]
    return {
        "policy": policy,
        "repetitions": len(vals),
        "admit_rate_mean": mean(admit),
        "admit_rate_std": pstdev(admit) if len(admit) > 1 else 0.0,
        "conditional_slo_attainment_mean": mean(cond),
        "conditional_slo_attainment_std": pstdev(cond) if len(cond) > 1 else 0.0,
        "effective_slo_goodput_mean": mean(goodput),
        "effective_slo_goodput_std": pstdev(goodput) if len(goodput) > 1 else 0.0,
        "p95_ttft_ms_mean": mean(p95) if p95 else None,
        "p95_ttft_ms_std": pstdev(p95) if len(p95) > 1 else 0.0,
        "p99_ttft_ms_mean": mean(p99) if p99 else None,
        "p99_ttft_ms_std": pstdev(p99) if len(p99) > 1 else 0.0,
        "throttle_rate_mean": mean(throttle),
        "throttle_rate_std": pstdev(throttle) if len(throttle) > 1 else 0.0,
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    header = [
        "policy",
        "repetitions",
        "admit_rate_mean",
        "admit_rate_std",
        "conditional_slo_attainment_mean",
        "conditional_slo_attainment_std",
        "effective_slo_goodput_mean",
        "effective_slo_goodput_std",
        "p95_ttft_ms_mean",
        "p95_ttft_ms_std",
        "p99_ttft_ms_mean",
        "p99_ttft_ms_std",
        "throttle_rate_mean",
        "throttle_rate_std",
    ]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(row[h]) for h in header))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_md(
    path: Path,
    rows: list[dict],
    selected: list[dict],
    rep_min: int,
    rep_max: int,
    *,
    title: str,
    burst_window: tuple[int, int] | None = None,
) -> None:
    by_policy: dict[str, list[dict]] = {}
    for row in selected:
        by_policy.setdefault(row["policy"], []).append(row)

    lines = [f"# {title}", ""]
    if burst_window:
        lines.append(f"Burst window: `{burst_window[0]}s..{burst_window[1]}s` from run start.")
    lines.append(f"Selection rule: latest run per `(policy, repetition)` for `r{rep_min}..r{rep_max}`.")
    lines.extend(
        [
            "",
            "| Policy | Reps | Admit | Conditional SLO | Effective SLO Goodput | P95 TTFT (ms) | P99 TTFT (ms) | Throttle |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| `{row['policy']}` | {row['repetitions']} | {row['admit_rate_mean']:.3f} | "
            f"{row['conditional_slo_attainment_mean']:.3f} | {row['effective_slo_goodput_mean']:.3f} | "
            f"{(row['p95_ttft_ms_mean'] or 0):.1f} | {(row['p99_ttft_ms_mean'] or 0):.1f} | {row['throttle_rate_mean']:.3f} |"
        )
    lines.extend(["", "## Selected runs", ""])
    for policy in sorted(by_policy):
        ordered = sorted(by_policy[policy], key=lambda r: r["rep"])
        parts = [f"r{r['rep']}: {r['run']}" for r in ordered]
        lines.append(f"- `{policy}`: " + "; ".join(parts))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _plot(path: Path, rows: list[dict], title: str) -> None:
    names = [r["policy"] for r in rows]
    goodput = [100 * r["effective_slo_goodput_mean"] for r in rows]
    p99 = [r["p99_ttft_ms_mean"] or 0 for r in rows]
    throttle = [100 * r["throttle_rate_mean"] for r in rows]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    fig.suptitle(title)
    axes[0].bar(names, goodput, capsize=3)
    axes[0].set_ylabel("Effective SLO goodput (%)")
    axes[0].set_ylim(0, 100)
    axes[0].tick_params(axis="x", rotation=30)
    axes[1].bar(names, p99, capsize=3)
    axes[1].set_ylabel("P99 TTFT (ms)")
    axes[1].tick_params(axis="x", rotation=30)
    axes[2].bar(names, throttle, capsize=3)
    axes[2].set_ylabel("Throttle rate (%)")
    axes[2].tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(path, dpi=160)


if __name__ == "__main__":
    main()
