#!/usr/bin/env python3
"""Aggregate load_sweep runs with frozen latest run selection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from runs import aggregate, load_summary_runs, plot_triple, select_latest, write_csv, write_selected_runs_md  # noqa: E402

CSV_COLUMNS = [
    "load_pct",
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("analysis/out"))
    parser.add_argument("--out", type=Path, default=Path("analysis/result_paper"))
    parser.add_argument("--scenario", default="load_sweep")
    parser.add_argument("--policy", default="none")
    parser.add_argument("--rep-min", type=int, default=1)
    parser.add_argument("--rep-max", type=int, default=5)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    runs = [r for r in load_summary_runs(args.input, args.scenario) if r["policy"] == args.policy]
    selected = select_latest(runs, ("load_pct", "rep"), args.rep_min, args.rep_max)
    rows = aggregate(selected, "load_pct")
    if not rows:
        raise SystemExit(f"no runs found for scenario={args.scenario} policy={args.policy}")

    stem = f"{args.scenario}_{args.policy}"
    write_csv(args.out / f"{stem}_summary.csv", rows, CSV_COLUMNS)
    _write_md(args.out / f"{stem}_summary.md", rows, selected, args.rep_min, args.rep_max)
    plot_triple(
        args.out / f"{stem}_summary.png",
        [r["load_pct"] for r in rows],
        goodput=[r["effective_slo_goodput_mean"] or 0 for r in rows],
        p99=[r["p99_ttft_ms_mean"] or 0 for r in rows],
        throttle=[r["throttle_rate_mean"] or 0 for r in rows],
        title=f"{args.scenario} ({args.policy})",
        kind="line",
        xlabel="Offered load (% C)",
        rotate_x=False,
    )
    print(f"wrote {args.out / f'{stem}_summary.png'}")


def _write_md(path: Path, rows: list[dict], selected: list[dict], rep_min: int, rep_max: int) -> None:
    lines = [
        "# Load Sweep Summary",
        "",
        f"Selection rule: latest run per `(load_pct, repetition)` for `r{rep_min}..r{rep_max}`.",
        "",
        "| Load | Reps | Admit | Conditional SLO | Effective SLO Goodput | P95 TTFT (ms) | P99 TTFT (ms) | Throttle |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['load_pct']}% | {row['repetitions']} | {row['admit_rate_mean']:.3f} | "
            f"{row['conditional_slo_attainment_mean']:.3f} | {row['effective_slo_goodput_mean']:.3f} | "
            f"{(row['p95_ttft_ms_mean'] or 0):.1f} | {(row['p99_ttft_ms_mean'] or 0):.1f} | {row['throttle_rate_mean']:.3f} |"
        )
    write_selected_runs_md(lines, selected, "load_pct")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
