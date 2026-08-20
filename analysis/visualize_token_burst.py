#!/usr/bin/env python3
"""Aggregate token_burst runs with frozen selection and burst-phase breakdown."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from metrics import load_events, summarize  # noqa: E402
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
    parser.add_argument("--input", type=Path, default=Path("analysis/out"))
    parser.add_argument("--out", type=Path, default=Path("analysis/result_paper"))
    parser.add_argument("--scenario", default="token_burst")
    parser.add_argument("--rep-min", type=int, default=1)
    parser.add_argument("--rep-max", type=int, default=5)
    parser.add_argument("--burst-start-s", type=int, default=180)
    parser.add_argument("--burst-end-s", type=int, default=360)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    selected = select_latest(load_summary_runs(args.input, args.scenario), ("policy", "rep"), args.rep_min, args.rep_max)
    if not selected:
        raise SystemExit(f"no runs found for scenario={args.scenario} in {args.input}")

    full_stats = aggregate(selected, "policy")
    burst_stats = _aggregate_burst(selected, args.burst_start_s, args.burst_end_s)
    stem = args.scenario
    columns = policy_csv_columns(include_p95=True)
    write_csv(args.out / f"{stem}_policy_summary.csv", full_stats, columns)
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
    plot_triple(
        args.out / f"{stem}_policy_summary.png",
        [r["policy"] for r in burst_stats],
        goodput=[r["effective_slo_goodput_mean"] or 0 for r in burst_stats],
        p99=[r["p99_ttft_ms_mean"] or 0 for r in burst_stats],
        throttle=[r["throttle_rate_mean"] or 0 for r in burst_stats],
        title="Token burst (burst phase)",
    )
    print(f"wrote {args.out / f'{stem}_policy_summary.png'}")


def _aggregate_burst(rows: list[dict], start_s: int, end_s: int) -> list[dict]:
    burst_rows: list[dict] = []
    for row in rows:
        events = load_events(row["run_dir"])
        if not events:
            continue
        t0 = min(e["arrival_ts"] for e in events)
        burst = [e for e in events if start_s <= e["arrival_ts"] - t0 < end_s]
        burst_rows.append({**row, "summary": summarize(burst)})
    return aggregate(burst_rows, "policy")


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
    write_selected_runs_md(lines, selected, "policy")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
