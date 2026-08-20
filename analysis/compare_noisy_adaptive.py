#!/usr/bin/env python3
"""Compare noisy_neighbor adaptive-slo vs static slo-aware (exclude victim)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import mean, pstdev

sys.path.insert(0, str(Path(__file__).parent))
from metrics import load_events, summarize  # noqa: E402
from runs import load_summary_runs, select_latest  # noqa: E402

VICTIM = "tenant-007"
METRICS = [
    "admit_rate",
    "conditional_slo_attainment",
    "effective_slo_goodput",
    "p99_ttft_ms",
    "throttle_rate",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adaptive-root", type=Path, default=Path("analysis/out"))
    parser.add_argument("--static-root", type=Path, default=Path("analysis/archive"))
    parser.add_argument("--out", type=Path, default=Path("analysis/result_paper/noisy_neighbor_adaptive_comparison.md"))
    args = parser.parse_args()

    adaptive = _latest_dirs(args.adaptive_root, "noisy_neighbor", "adaptive-slo")
    static = _latest_dirs(args.static_root, "noisy_neighbor", "slo-aware")
    if not adaptive:
        raise SystemExit("no adaptive-slo noisy_neighbor runs found")
    if not static:
        raise SystemExit("no static slo-aware noisy_neighbor runs found")

    rows = []
    for label, runs in (("adaptive-slo", adaptive), ("slo-aware", static)):
        summaries = [_non_victim_summary(r) for r in runs]
        rows.append(_agg(label, summaries, runs))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_markdown(rows), encoding="utf-8")
    print(args.out.read_text())
    print(f"wrote {args.out}")


def _latest_dirs(root: Path, scenario: str, policy: str) -> list[Path]:
    runs = [r for r in load_summary_runs(root, scenario) if r["policy"] == policy]
    return [r["run_dir"] for r in select_latest(runs, ("policy", "rep"), 1, 5)]


def _non_victim_summary(run_dir: Path) -> dict:
    events = load_events(run_dir)
    non = [e for e in events if e.get("tenant_id") != VICTIM]
    summary = summarize(non)
    by_tier = {}
    for tier in ("P1", "P2", "P3"):
        te = [e for e in non if e.get("tier") == tier]
        if te:
            by_tier[tier] = summarize(te)
    summary["_by_tier"] = by_tier
    summary["_run"] = run_dir.name
    return summary


def _agg(label: str, summaries: list[dict], runs: list[Path]) -> dict:
    out = {"policy": label, "reps": len(summaries), "runs": [r.name for r in runs]}
    for m in METRICS:
        xs = [s[m] for s in summaries if s.get(m) is not None]
        out[f"{m}_mean"] = mean(xs)
        out[f"{m}_std"] = pstdev(xs) if len(xs) > 1 else 0.0
    for tier in ("P1", "P2", "P3"):
        for m in ("admit_rate", "conditional_slo_attainment", "effective_slo_goodput", "p99_ttft_ms"):
            xs = []
            for s in summaries:
                t = s.get("_by_tier", {}).get(tier)
                if t and t.get(m) is not None:
                    xs.append(t[m])
            if xs:
                out[f"{tier}_{m}_mean"] = mean(xs)
                out[f"{tier}_{m}_std"] = pstdev(xs) if len(xs) > 1 else 0.0
    return out


def _markdown(rows: list[dict]) -> str:
    lines = [
        "# Noisy Neighbor: Adaptive vs Static SLO-aware",
        "",
        "Metrics exclude victim `tenant-007`. Selection: latest `r1..r5` per policy.",
        "",
        "## Overall (non-victim)",
        "",
        "| Policy | Reps | Admit | Cond. SLO | Effective goodput | P99 TTFT | Throttle |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['policy']}` | {r['reps']} | "
            f"{r['admit_rate_mean']:.3f} ± {r['admit_rate_std']:.3f} | "
            f"{r['conditional_slo_attainment_mean']:.3f} ± {r['conditional_slo_attainment_std']:.3f} | "
            f"{r['effective_slo_goodput_mean']:.3f} ± {r['effective_slo_goodput_std']:.3f} | "
            f"{r['p99_ttft_ms_mean']:.0f} ± {r['p99_ttft_ms_std']:.0f} | "
            f"{r['throttle_rate_mean']:.3f} ± {r['throttle_rate_std']:.3f} |"
        )
    lines += ["", "## By tier (non-victim)", ""]
    for tier in ("P1", "P2", "P3"):
        lines += [
            f"### {tier}",
            "",
            "| Policy | Admit | Cond. SLO | Effective goodput | P99 TTFT |",
            "|---|---:|---:|---:|---:|",
        ]
        for r in rows:
            if f"{tier}_admit_rate_mean" not in r:
                continue
            lines.append(
                f"| `{r['policy']}` | "
                f"{r[f'{tier}_admit_rate_mean']:.3f} | "
                f"{r[f'{tier}_conditional_slo_attainment_mean']:.3f} | "
                f"{r[f'{tier}_effective_slo_goodput_mean']:.3f} | "
                f"{r[f'{tier}_p99_ttft_ms_mean']:.0f} |"
            )
        lines.append("")
    lines += ["## Selected runs", ""]
    for r in rows:
        lines.append(f"- `{r['policy']}`: " + "; ".join(r["runs"]))
    lines += [
        "",
        "## Interpretation checklist",
        "",
        "- Does adaptive keep P1/P2 SLO near static?",
        "- Does non-offender P99 stay close to static, or does admit≈1 inflate tails?",
        "- Is goodput gain worth isolation loss?",
        "",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
