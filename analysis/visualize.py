#!/usr/bin/env python3
"""Policy-level aggregation with frozen run selection.

Input runs live under `analysis/archive/*/summary.json` (raw run folders).
This script selects the latest run for each `(policy, repetition)` and writes
paper-ready artifacts to `analysis/result_paper/`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from runs import (  # noqa: E402
    aggregate,
    load_summary_runs,
    plot_triple,
    policy_csv_columns,
    select_latest,
    write_csv,
    write_selected_runs_md,
)


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
    runs = load_summary_runs(args.input, args.scenario)
    if not runs:
        raise SystemExit(f"no summary.json found for scenario '{args.scenario}' in {args.input}")

    selected = select_latest(runs, ("policy", "load_pct", "rep"), args.rep_min, args.rep_max)
    if not selected:
        raise SystemExit("no runs match selected repetition window")

    stats = aggregate(selected, "policy")
    _write_csv(args.out / f"{args.scenario}_policy_summary.csv", stats)
    chart = args.out / f"{args.scenario}_policy_summary.png"
    _plot(chart, stats, args.title)
    _write_markdown(
        args.out / f"{args.scenario}_all_policies_summary.md",
        stats,
        selected,
        args.scenario,
        args.rep_min,
        args.rep_max,
    )
    print(f"wrote {chart}")


def _write_csv(path: Path, rows: list[dict]) -> None:
    write_csv(path, rows, policy_csv_columns())


def _plot(path: Path, rows: list[dict], title: str) -> None:
    plot_triple(
        path,
        [r["policy"] for r in rows],
        goodput=[r["effective_slo_goodput_mean"] or 0 for r in rows],
        p99=[r["p99_ttft_ms_mean"] or 0 for r in rows],
        throttle=[r["throttle_rate_mean"] or 0 for r in rows],
        title=title,
        goodput_err=[r["effective_slo_goodput_std"] for r in rows],
        p99_err=[r["p99_ttft_ms_std"] for r in rows],
        throttle_err=[r["throttle_rate_std"] for r in rows],
    )


def _write_markdown(
    path: Path,
    rows: list[dict],
    selected: list[dict],
    scenario: str,
    rep_min: int,
    rep_max: int,
) -> None:
    title = scenario.replace("_", " ").title()
    lines = [
        f"# {title} All-Policies Summary",
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
            f"{(row['p99_ttft_ms_mean'] or 0):.1f} | {row['throttle_rate_mean']:.3f} |"
        )
    write_selected_runs_md(
        lines,
        selected,
        "policy",
        heading="## Selected runs (per policy, repetition)",
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
