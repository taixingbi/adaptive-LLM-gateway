#!/usr/bin/env python3
"""Policy-level aggregation with frozen run selection.

Input runs live under `analysis/archive/*/summary.json` (raw run folders).
This script selects the latest run for each `(policy, repetition)` and writes
paper-ready artifacts to `analysis/result_paper/`.
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
    parser.add_argument("--rep-min", type=int, default=1)
    parser.add_argument("--rep-max", type=int, default=5)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    runs = _load_runs(args.input, args.scenario)
    if not runs:
        raise SystemExit(f"no summary.json found for scenario '{args.scenario}' in {args.input}")

    selected = _select_latest_repetitions(runs, args.rep_min, args.rep_max)
    if not selected:
        raise SystemExit("no runs match selected repetition window")

    stats = _aggregate(selected)
    _write_csv(args.out / f"{args.scenario}_policy_summary.csv", stats)
    chart = args.out / f"{args.scenario}_policy_summary.png"
    _plot(chart, stats, args.title)
    _write_markdown(args.out / f"{args.scenario}_all_policies_summary.md", stats, selected, args.rep_min, args.rep_max)
    print(f"wrote {chart}")


def _load_runs(out_dir: Path, scenario: str) -> list[dict]:
    pattern = re.compile(rf"{re.escape(scenario)}-([a-z\-]+?)(?:-(\d+)pct)?-r(\d+)-")
    rows: list[dict] = []
    for file in out_dir.glob(f"{scenario}-*/summary.json"):
        match = pattern.match(file.parent.name)
        if not match:
            continue
        policy = match.group(1)
        load_pct = int(match.group(2)) if match.group(2) is not None else None
        rep = int(match.group(3))
        summary = json.loads(file.read_text(encoding="utf-8"))
        rows.append(
            {
                "policy": policy,
                "load_pct": load_pct,
                "rep": rep,
                "summary": summary,
                "run": file.parent.name,
                "ts": file.parent.name.rsplit("-", 1)[-1],
            }
        )
    return rows


def _select_latest_repetitions(rows: list[dict], rep_min: int, rep_max: int) -> list[dict]:
    latest: dict[tuple[str, int], dict] = {}
    for row in rows:
        rep = row["rep"]
        if rep < rep_min or rep > rep_max:
            continue
        key = (row["policy"], row.get("load_pct"), rep)
        prev = latest.get(key)
        if prev is None or row["run"] > prev["run"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda r: (r["policy"], r["rep"]))


def _aggregate(rows: list[dict]) -> list[dict]:
    by_policy: dict[str, list[dict]] = {}
    for row in rows:
        by_policy.setdefault(row["policy"], []).append(row)

    metrics = [
        "admit_rate",
        "conditional_slo_attainment",
        "effective_slo_goodput",
        "p99_ttft_ms",
        "throttle_rate",
    ]
    out: list[dict] = []
    for policy in sorted(by_policy):
        policy_rows = by_policy[policy]
        values = [r["summary"] for r in policy_rows]
        agg = {"policy": policy, "repetitions": len(values)}
        for metric in metrics:
            if metric == "effective_slo_goodput":
                col = [
                    (
                        v.get("effective_slo_goodput")
                        if v.get("effective_slo_goodput") is not None
                        else (v.get("slo_goodput") if v.get("slo_goodput") is not None else v.get("admit_rate", 0.0) * v.get("slo_attainment", 0.0))
                    )
                    for v in values
                ]
            elif metric == "conditional_slo_attainment":
                col = [
                    (v.get("conditional_slo_attainment") if v.get("conditional_slo_attainment") is not None else v.get("slo_attainment"))
                    for v in values
                    if v.get("slo_attainment") is not None or v.get("conditional_slo_attainment") is not None
                ]
            else:
                col = [v[metric] for v in values if v.get(metric) is not None]
            agg[f"{metric}_mean"] = mean(col)
            agg[f"{metric}_std"] = pstdev(col) if len(col) > 1 else 0.0
        agg["selected_runs"] = [r["run"] for r in sorted(policy_rows, key=lambda x: x["rep"])]
        out.append(agg)
    return out


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
    goodput_mean = [100 * r["effective_slo_goodput_mean"] for r in rows]
    goodput_std = [100 * r["effective_slo_goodput_std"] for r in rows]
    p99_mean = [r["p99_ttft_ms_mean"] for r in rows]
    p99_std = [r["p99_ttft_ms_std"] for r in rows]
    thr_mean = [100 * r["throttle_rate_mean"] for r in rows]
    thr_std = [100 * r["throttle_rate_std"] for r in rows]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    fig.suptitle(title)

    axes[0].bar(names, goodput_mean, yerr=goodput_std, capsize=3)
    axes[0].set_ylabel("Effective SLO goodput (%)")
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


def _write_markdown(path: Path, rows: list[dict], selected: list[dict], rep_min: int, rep_max: int) -> None:
    by_policy_runs: dict[str, list[dict]] = {}
    for row in selected:
        by_policy_runs.setdefault(row["policy"], []).append(row)

    lines = [
        "# Noisy Neighbor All-Policies Summary",
        "",
        f"Selection rule: latest run per `(policy, repetition)` for `r{rep_min}..r{rep_max}` (based on timestamp in run folder name).",
        "",
        "| Policy | Reps | Admit rate | Conditional SLO | Effective SLO Goodput | P99 TTFT (ms) | Throttle rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['policy']}` | {row['repetitions']} | {row['admit_rate_mean']:.3f} | "
            f"{row['conditional_slo_attainment_mean']:.3f} | {row['effective_slo_goodput_mean']:.3f} | "
            f"{row['p99_ttft_ms_mean']:.1f} | {row['throttle_rate_mean']:.3f} |"
        )
    lines.extend(["", "## Selected runs (per policy, repetition)", ""])
    for policy in sorted(by_policy_runs):
        ordered = sorted(by_policy_runs[policy], key=lambda r: r["rep"])
        parts = [
            (
                f"{r['load_pct']}pct-r{r['rep']}: {r['run']}"
                if r.get("load_pct") is not None
                else f"r{r['rep']}: {r['run']}"
            )
            for r in ordered
        ]
        lines.append(f"- `{policy}`: " + "; ".join(parts))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
