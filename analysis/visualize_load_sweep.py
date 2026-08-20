#!/usr/bin/env python3
"""Aggregate load_sweep runs with frozen latest run selection."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from statistics import mean, pstdev

import matplotlib.pyplot as plt


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
    runs = _load_runs(args.input, args.scenario, args.policy)
    selected = _select_latest(runs, args.rep_min, args.rep_max)
    rows = _aggregate(selected)
    if not rows:
        raise SystemExit(f"no runs found for scenario={args.scenario} policy={args.policy}")

    stem = f"{args.scenario}_{args.policy}"
    _write_csv(args.out / f"{stem}_summary.csv", rows)
    _write_md(args.out / f"{stem}_summary.md", rows, selected, args.rep_min, args.rep_max)
    _plot(args.out / f"{stem}_summary.png", rows, f"{args.scenario} ({args.policy})")
    print(f"wrote {args.out / f'{stem}_summary.png'}")


def _load_runs(root: Path, scenario: str, policy: str) -> list[dict]:
    pattern = re.compile(rf"{re.escape(scenario)}-{re.escape(policy)}-(\d+)pct-r(\d+)-")
    rows: list[dict] = []
    for file in root.glob(f"{scenario}-{policy}-*pct-r*/summary.json"):
        m = pattern.match(file.parent.name)
        if not m:
            continue
        load_pct = int(m.group(1))
        rep = int(m.group(2))
        summary = json.loads(file.read_text(encoding="utf-8"))
        rows.append({"load_pct": load_pct, "rep": rep, "run": file.parent.name, "summary": summary})
    return rows


def _select_latest(rows: list[dict], rep_min: int, rep_max: int) -> list[dict]:
    latest: dict[tuple[int, int], dict] = {}
    for row in rows:
        if row["rep"] < rep_min or row["rep"] > rep_max:
            continue
        key = (row["load_pct"], row["rep"])
        prev = latest.get(key)
        if prev is None or row["run"] > prev["run"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda x: (x["load_pct"], x["rep"]))


def _aggregate(rows: list[dict]) -> list[dict]:
    by_load: dict[int, list[dict]] = {}
    for row in rows:
        by_load.setdefault(row["load_pct"], []).append(row)

    out: list[dict] = []
    for load_pct in sorted(by_load):
        vals = [r["summary"] for r in by_load[load_pct]]
        cond = [v.get("conditional_slo_attainment", v.get("slo_attainment")) for v in vals]
        goodput = [
            v.get("effective_slo_goodput", v.get("slo_goodput", v.get("admit_rate", 0.0) * v.get("slo_attainment", 0.0)))
            for v in vals
        ]
        p99 = [v.get("p99_ttft_ms") for v in vals if v.get("p99_ttft_ms") is not None]
        p95 = [v.get("p95_ttft_ms") for v in vals if v.get("p95_ttft_ms") is not None]
        admit = [v.get("admit_rate") for v in vals if v.get("admit_rate") is not None]
        throttle = [v.get("throttle_rate") for v in vals if v.get("throttle_rate") is not None]
        out.append(
            {
                "load_pct": load_pct,
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
        )
    return out


def _write_csv(path: Path, rows: list[dict]) -> None:
    header = [
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
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(row[h]) for h in header))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_md(path: Path, rows: list[dict], selected: list[dict], rep_min: int, rep_max: int) -> None:
    by_load: dict[int, list[dict]] = {}
    for row in selected:
        by_load.setdefault(row["load_pct"], []).append(row)
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
    lines.extend(["", "## Selected runs", ""])
    for load_pct in sorted(by_load):
        ordered = sorted(by_load[load_pct], key=lambda x: x["rep"])
        parts = [f"r{r['rep']}: {r['run']}" for r in ordered]
        lines.append(f"- `{load_pct}%`: " + "; ".join(parts))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _plot(path: Path, rows: list[dict], title: str) -> None:
    x = [r["load_pct"] for r in rows]
    goodput = [100 * r["effective_slo_goodput_mean"] for r in rows]
    p99 = [r["p99_ttft_ms_mean"] or 0 for r in rows]
    throttle = [100 * r["throttle_rate_mean"] for r in rows]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    fig.suptitle(title)
    axes[0].plot(x, goodput, marker="o")
    axes[0].set_ylabel("Effective SLO goodput (%)")
    axes[0].set_xlabel("Offered load (% C)")
    axes[0].set_ylim(0, 100)
    axes[1].plot(x, p99, marker="o")
    axes[1].set_ylabel("P99 TTFT (ms)")
    axes[1].set_xlabel("Offered load (% C)")
    axes[2].plot(x, throttle, marker="o")
    axes[2].set_ylabel("Throttle rate (%)")
    axes[2].set_xlabel("Offered load (% C)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)


if __name__ == "__main__":
    main()
