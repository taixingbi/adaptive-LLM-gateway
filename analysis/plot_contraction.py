#!/usr/bin/env python3
"""Contraction / recovery figure and controller timings for provider_contraction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean, pstdev

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from metrics import load_events, summarize  # noqa: E402
from plot_adaptive_trace import bin_trace  # noqa: E402
from runs import load_summary_runs, select_latest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("analysis/out"))
    parser.add_argument("--out", type=Path, default=Path("analysis/result_paper"))
    parser.add_argument("--scenario", default="provider_contraction")
    parser.add_argument("--bin-s", type=float, default=5.0)
    parser.add_argument("--pressure-start-s", type=float, default=360)
    parser.add_argument("--pressure-end-s", type=float, default=600)
    parser.add_argument("--rep-min", type=int, default=1)
    parser.add_argument("--rep-max", type=int, default=5)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    selected = select_latest(load_summary_runs(args.input, args.scenario), ("policy", "rep"), args.rep_min, args.rep_max)
    if not selected:
        raise SystemExit(f"no runs found for scenario={args.scenario}")

    rows = []
    for run in selected:
        events = load_events(run["run_dir"])
        if not events:
            continue
        background = _load_background(run["run_dir"])
        trace = bin_trace(events, args.bin_s)
        metrics = contraction_metrics(trace, events, args.pressure_start_s, args.pressure_end_s)
        metrics["rep"] = run["rep"]
        metrics["run"] = run["run"]
        rows.append(metrics)
        _plot_run(
            trace,
            background,
            args.out / f"contraction_trace_r{run['rep']}.png",
            run["run"],
            args.pressure_start_s,
            args.pressure_end_s,
            args.bin_s,
        )

    summary = _aggregate(rows)
    (args.out / "contraction_metrics.json").write_text(json.dumps({"runs": rows, "mean": summary}, indent=2), encoding="utf-8")
    (args.out / "contraction_metrics.md").write_text(_markdown(rows, summary, args.pressure_start_s, args.pressure_end_s), encoding="utf-8")
    print(f"wrote {args.out / 'contraction_metrics.md'}")


def contraction_metrics(trace: dict[str, list], events: list[dict], start_s: float, end_s: float) -> dict:
    t0 = min(e["arrival_ts"] for e in events)
    pre_caps = [
        float(e["adaptive_capacity"])
        for e in events
        if e.get("adaptive_capacity") is not None and start_s - 60 <= e["arrival_ts"] - t0 < start_s
    ]
    if not pre_caps:
        pre_caps = [
            float(e["adaptive_capacity"])
            for e in events
            if e.get("adaptive_capacity") is not None and e["arrival_ts"] - t0 < start_s
        ]
    pre = mean(pre_caps) if pre_caps else None
    pressure_t = _first_pressure(events, t0, start_s, end_s)
    t20 = _first_capacity(trace, pressure_t or start_s, lambda c: pre is not None and c <= 0.8 * pre)
    t50 = _first_capacity(trace, pressure_t or start_s, lambda c: pre is not None and c <= 0.5 * pre)
    t90 = _first_capacity(trace, end_s, lambda c: pre is not None and c >= 0.9 * pre)
    phase = [e for e in events if start_s <= e["arrival_ts"] - t0 < end_s]
    phase_summary = summarize(phase)
    return {
        "pre_capacity": pre,
        "pressure_t_s": pressure_t,
        "t_contract_20_s": None if t20 is None or pressure_t is None else t20 - pressure_t,
        "t_contract_50_s": None if t50 is None or pressure_t is None else t50 - pressure_t,
        "t_recover_90_s": None if t90 is None else t90 - end_s,
        "t_contract_20_abs_s": t20,
        "t_contract_50_abs_s": t50,
        "t_recover_90_abs_s": t90,
        "contraction_slo_fail_rate": 1.0 - phase_summary["conditional_slo_attainment"],
        "contraction_429_rate": phase_summary["bedrock_429_rate"],
        "contraction_effective_slo_goodput": phase_summary["effective_slo_goodput"],
        "contraction_admit_rate": phase_summary["admit_rate"],
        "contraction_p99_ttft_ms": phase_summary["p99_ttft_ms"],
    }


def _first_pressure(events: list[dict], t0: float, start_s: float, end_s: float) -> float | None:
    for event in sorted(events, key=lambda e: e["arrival_ts"]):
        t = event["arrival_ts"] - t0
        if t < start_s or t >= end_s:
            continue
        if event.get("bedrock_429") or (event.get("decision") == "ADMIT" and event.get("slo_met") is False):
            return t
    return None


def _first_capacity(trace: dict[str, list], after_s: float, pred) -> float | None:
    for t, cap in zip(trace["t_s"], trace["adaptive_capacity"]):
        if t < after_s or cap is None:
            continue
        if pred(float(cap)):
            return float(t)
    return None


def _load_background(run_dir: Path) -> list[dict]:
    path = run_dir / "background.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _plot_run(
    trace: dict[str, list],
    background: list[dict],
    out: Path,
    title: str,
    start_s: float,
    end_s: float,
    bin_s: float,
) -> None:
    bg_xs, bg_rps, bg_429 = _bin_background(background, bin_s)
    fig, axes = plt.subplots(4, 1, figsize=(10, 11), sharex=True)
    fig.suptitle(f"Provider contraction — {title}")
    axes[0].plot(bg_xs, bg_rps, marker=".", label="background req/s")
    axes[0].plot(bg_xs, [1000 * r for r in bg_429], marker=".", label="background 429 ×1000")
    axes[0].axvspan(start_s, end_s, color="tab:red", alpha=0.08)
    axes[0].set_ylabel("Background load")
    axes[0].legend()
    axes[1].plot(trace["t_s"], trace["adaptive_capacity"], marker=".")
    axes[1].axvspan(start_s, end_s, color="tab:red", alpha=0.08)
    axes[1].set_ylabel("Adaptive C_hat")
    axes[2].plot(trace["t_s"], trace["p99_ttft_ms"], marker=".", label="P99")
    axes[2].plot(trace["t_s"], [1000 * r for r in trace["bedrock_429_rate"]], marker=".", label="429 ×1000")
    axes[2].axvspan(start_s, end_s, color="tab:red", alpha=0.08)
    axes[2].set_ylabel("P99 / 429")
    axes[2].legend()
    axes[3].plot(trace["t_s"], [100 * a for a in trace["admit_rate"]], marker=".")
    axes[3].axvspan(start_s, end_s, color="tab:red", alpha=0.08)
    axes[3].set_ylabel("Admit rate (%)")
    axes[3].set_xlabel("Time (s)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _bin_background(events: list[dict], bin_s: float) -> tuple[list[float], list[float], list[float]]:
    if not events:
        return [], [], []
    t0 = min(e["start_ts"] for e in events)
    bins: dict[int, list[dict]] = {}
    for event in events:
        bins.setdefault(int((event["start_ts"] - t0) // bin_s), []).append(event)
    xs, rps, r429 = [], [], []
    for b in sorted(bins):
        rows = bins[b]
        xs.append(b * bin_s)
        rps.append(len(rows) / bin_s)
        r429.append(sum(1 for e in rows if e.get("bedrock_429")) / max(len(rows), 1))
    return xs, rps, r429


def _aggregate(rows: list[dict]) -> dict:
    keys = [
        "pre_capacity",
        "t_contract_20_s",
        "t_contract_50_s",
        "t_recover_90_s",
        "contraction_slo_fail_rate",
        "contraction_429_rate",
        "contraction_effective_slo_goodput",
        "contraction_admit_rate",
        "contraction_p99_ttft_ms",
    ]
    out = {}
    for key in keys:
        xs = [r[key] for r in rows if r.get(key) is not None]
        out[f"{key}_mean"] = mean(xs) if xs else None
        out[f"{key}_std"] = pstdev(xs) if len(xs) > 1 else 0.0
        out[f"{key}_n"] = len(xs)
    return out


def _markdown(rows: list[dict], summary: dict, start_s: float, end_s: float) -> str:
    lines = [
        "# Provider contraction / recovery",
        "",
        f"Background pressure window: `{start_s:.0f}–{end_s:.0f}s`. Ĉ reset to C0 before each rep.",
        "",
        "| Metric | Mean | Std | n |",
        "|---|---:|---:|---:|",
    ]
    labels = [
        ("pre_capacity", "Pre-pressure Ĉ"),
        ("t_contract_20_s", "T_contract to −20% (s)"),
        ("t_contract_50_s", "T_contract to −50% (s)"),
        ("t_recover_90_s", "T_recover to 90% (s)"),
        ("contraction_slo_fail_rate", "Contraction SLO-fail rate"),
        ("contraction_429_rate", "Contraction 429 rate"),
        ("contraction_effective_slo_goodput", "Contraction effective goodput"),
        ("contraction_admit_rate", "Contraction admit rate"),
        ("contraction_p99_ttft_ms", "Contraction P99 TTFT (ms)"),
    ]
    for key, label in labels:
        mean_v, std_v, n = summary[f"{key}_mean"], summary[f"{key}_std"], summary[f"{key}_n"]
        if mean_v is None:
            lines.append(f"| {label} | — | — | {n} |")
        else:
            lines.append(f"| {label} | {mean_v:.3f} | {std_v:.3f} | {n} |")
    lines.extend(["", "## Per-rep", ""])
    for row in rows:
        lines.append(f"- r{row['rep']}: `{row['run']}` Ĉ_pre={row['pre_capacity']}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
