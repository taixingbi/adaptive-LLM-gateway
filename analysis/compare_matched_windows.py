#!/usr/bin/env python3
"""Matched-window Table IV: four cells, burst t ∈ [120, 300), per-rep then sample SD."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from statistics import mean, stdev

sys.path.insert(0, str(Path(__file__).parent))
from metrics import load_events, summarize  # noqa: E402
from runs import load_summary_runs, plot_triple, select_latest, write_selected_runs_md  # noqa: E402

BURST_START_S = 120
BURST_END_S = 300
ADAPTIVE_MIN_STAMP = "20261021-1938"
METRICS = (
    ("admit_rate", "admit"),
    ("effective_slo_goodput", "goodput"),
    ("conditional_slo_attainment", "cond_slo"),
    ("p99_ttft_ms", "p99_ms"),
    ("throttle_rate", "throttle"),
    ("bedrock_429_rate", "bedrock_429"),
)

CELLS = (
    {
        "name": "NONE",
        "plot": "NONE",
        "scenario": "token_burst_coldstart_c100k",
        "policy": "none",
        "budget_tag": "100k",
        "min_stamp": None,
    },
    {
        "name": "STATIC-SLO @ C0",
        "plot": "SLO @ C0",
        "scenario": "token_burst_coldstart_c100k",
        "policy": "slo-aware",
        "budget_tag": "100k",
        "min_stamp": None,
    },
    {
        "name": "STATIC-SLO @ Cmax",
        "plot": "SLO @ Cmax",
        "scenario": "token_burst_coldstart_c2m",
        "policy": "slo-aware",
        "budget_tag": "2M",
        "min_stamp": None,
    },
    {
        "name": "Adaptive-cold",
        "plot": "Adaptive",
        "scenario": "token_burst_coldstart",
        "policy": "adaptive-slo",
        "budget_tag": "100k",
        "min_stamp": ADAPTIVE_MIN_STAMP,
    },
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("analysis/out"))
    parser.add_argument("--out", type=Path, default=Path("analysis/result_paper"))
    parser.add_argument("--burst-start-s", type=int, default=BURST_START_S)
    parser.add_argument("--burst-end-s", type=int, default=BURST_END_S)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cells = [
        _cell(
            args.input,
            spec,
            args.burst_start_s,
            args.burst_end_s,
        )
        for spec in CELLS
    ]

    path_md = args.out / "token_burst_matched_summary.md"
    path_csv = args.out / "token_burst_matched_summary.csv"
    path_png = args.out / "token_burst_matched_tradeoff.png"
    path_md.write_text(_markdown(cells, args.burst_start_s, args.burst_end_s), encoding="utf-8")
    _write_csv(path_csv, cells)
    _plot(path_png, cells, args.burst_start_s, args.burst_end_s)
    print(path_md.read_text())
    print(f"wrote {path_md}")
    print(f"wrote {path_csv}")
    print(f"wrote {path_png}")


def _cell(root: Path, spec: dict, start_s: int, end_s: int) -> dict:
    runs = [
        r
        for r in select_latest(
            load_summary_runs(root, spec["scenario"]),
            ("policy", "budget_tag", "rep"),
            1,
            5,
        )
        if r["policy"] == spec["policy"]
        and (r.get("budget_tag") or "").lower() == spec["budget_tag"].lower()
        and (spec["min_stamp"] is None or _run_stamp(r["run"]) >= spec["min_stamp"])
    ]
    out = {
        "name": spec["name"],
        "plot": spec["plot"],
        "scenario": spec["scenario"],
        "policy": spec["policy"],
        "budget_tag": spec["budget_tag"],
        "runs": [r["run"] for r in sorted(runs, key=lambda x: x["rep"])],
        "reps": [],
        "missing": False,
    }
    if not runs:
        out["missing"] = True
        out["source"] = f"no {spec['scenario']}/{spec['policy']}/c{spec['budget_tag']} r1–r5"
        return out

    summaries = []
    for run in sorted(runs, key=lambda x: x["rep"]):
        events = [e for e in load_events(run["run_dir"]) if e.get("arrival_ts") is not None]
        if not events:
            continue
        t0 = min(e["arrival_ts"] for e in events)
        burst = [e for e in events if start_s <= e["arrival_ts"] - t0 < end_s]
        summary = summarize(burst)
        summary["_run"] = run["run"]
        summary["_rep"] = run["rep"]
        summaries.append(summary)

    if not summaries:
        out["missing"] = True
        out["source"] = f"empty burst window for {spec['policy']}-c{spec['budget_tag']}"
        return out

    out["reps"] = summaries
    out["repetitions"] = len(summaries)
    out["source"] = f"{spec['scenario']} {spec['policy']} c{spec['budget_tag']}"
    for metric, key in METRICS:
        values = [s.get(metric) for s in summaries if s.get(metric) is not None]
        out[f"{key}_mean"], out[f"{key}_std"] = _mean_sd(values)
    return out


def _mean_sd(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    return mean(values), (stdev(values) if len(values) > 1 else 0.0)


def _run_stamp(run: str) -> str:
    parts = run.rsplit("-", 2)
    if len(parts) < 3:
        return run
    return f"{parts[-2]}-{parts[-1]}"


def _fmt(mean_v: float | None, std_v: float | None, *, digits: int = 3, unit: str = "") -> str:
    if mean_v is None:
        return "—"
    body = f"{mean_v:.{digits}f}±{0.0 if std_v is None else std_v:.{digits}f}"
    return f"{body}{unit}"


def _markdown(cells: list[dict], start_s: int, end_s: int) -> str:
    lines = [
        "# Token burst: matched-window Table IV",
        "",
        f"Burst window `{start_s}–{end_s}s` from each run’s `min(arrival_ts)`. "
        "Each repetition is summarized first; cells report mean ± sample SD "
        "(`statistics.stdev`, n−1). Requests are not pooled across repetitions.",
        "",
        "Adaptive-cold reuses the existing `token_burst_coldstart` health-fix "
        f"runs (stamp ≥ {ADAPTIVE_MIN_STAMP}). "
        "`token_burst_static_cmax.md` remains the unmatched 180–360s archive.",
        "",
        "| Cell | Admit | Effective goodput | Conditional SLO | P99 TTFT | Throttle | Bedrock 429 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in cells:
        if cell.get("missing"):
            lines.append(f"| {cell['name']} | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {cell['name']} | {_fmt(cell['admit_mean'], cell['admit_std'])} | "
            f"{_fmt(cell['goodput_mean'], cell['goodput_std'])} | "
            f"{_fmt(cell['cond_slo_mean'], cell['cond_slo_std'])} | "
            f"{_fmt(cell['p99_ms_mean'], cell['p99_ms_std'], digits=0, unit=' ms')} | "
            f"{_fmt(cell['throttle_mean'], cell['throttle_std'])} | "
            f"{_fmt(cell['bedrock_429_mean'], cell['bedrock_429_std'])} |"
        )
    selected = []
    for cell in cells:
        for summary in cell.get("reps") or []:
            selected.append(
                {"policy": cell["name"], "rep": summary["_rep"], "run": summary["_run"]}
            )
    write_selected_runs_md(lines, selected, "policy")
    lines.append("")
    return "\n".join(lines)


def _write_csv(path: Path, cells: list[dict]) -> None:
    cols = [
        "cell",
        "repetitions",
        "admit_mean",
        "admit_std",
        "goodput_mean",
        "goodput_std",
        "cond_slo_mean",
        "cond_slo_std",
        "p99_ms_mean",
        "p99_ms_std",
        "throttle_mean",
        "throttle_std",
        "bedrock_429_mean",
        "bedrock_429_std",
        "source",
        "runs",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for cell in cells:
            writer.writerow(
                {
                    "cell": cell["name"],
                    "repetitions": cell.get("repetitions", 0),
                    "admit_mean": cell.get("admit_mean", ""),
                    "admit_std": cell.get("admit_std", ""),
                    "goodput_mean": cell.get("goodput_mean", ""),
                    "goodput_std": cell.get("goodput_std", ""),
                    "cond_slo_mean": cell.get("cond_slo_mean", ""),
                    "cond_slo_std": cell.get("cond_slo_std", ""),
                    "p99_ms_mean": cell.get("p99_ms_mean", ""),
                    "p99_ms_std": cell.get("p99_ms_std", ""),
                    "throttle_mean": cell.get("throttle_mean", ""),
                    "throttle_std": cell.get("throttle_std", ""),
                    "bedrock_429_mean": cell.get("bedrock_429_mean", ""),
                    "bedrock_429_std": cell.get("bedrock_429_std", ""),
                    "source": cell.get("source", ""),
                    "runs": ";".join(cell.get("runs") or []),
                }
            )


def _plot(path: Path, cells: list[dict], start_s: int, end_s: int) -> None:
    ready = [c for c in cells if not c.get("missing")]
    if not ready:
        return
    plot_triple(
        path,
        [c["plot"] for c in ready],
        goodput=[c["goodput_mean"] or 0.0 for c in ready],
        p99=[c["p99_ms_mean"] or 0.0 for c in ready],
        throttle=[c["throttle_mean"] or 0.0 for c in ready],
        goodput_err=[c["goodput_std"] or 0.0 for c in ready],
        p99_err=[c["p99_ms_std"] or 0.0 for c in ready],
        throttle_err=[c["throttle_std"] or 0.0 for c in ready],
        title=f"Matched-window token burst ({start_s}–{end_s}s)",
    )


if __name__ == "__main__":
    main()
