#!/usr/bin/env python3
"""Static-Cmax vs C0 vs adaptive (token-burst burst window). Reuses frozen NONE / STATIC-C0."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from metrics import load_events, summarize  # noqa: E402
from runs import load_summary_runs, select_latest  # noqa: E402

# Burst-phase numbers from analysis/result_paper/token_burst_comparison.md
FROZEN = {
    "NONE": {
        "admit": 1.000,
        "goodput": 1.000,
        "cond_slo": 1.000,
        "p99_ms": 566,
        "throttle": 0.000,
        "source": "frozen token_burst none",
    },
    "STATIC-SLO @ C0=100k": {
        "admit": 0.049,
        "goodput": 0.046,
        "cond_slo": 0.949,
        "p99_ms": 398,
        "throttle": 0.951,
        "source": "frozen token_burst slo-aware",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("analysis/out"))
    parser.add_argument("--out", type=Path, default=Path("analysis/result_paper"))
    parser.add_argument("--burst-start-s", type=int, default=180)
    parser.add_argument("--burst-end-s", type=int, default=360)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cells = dict(FROZEN)
    cells["STATIC-SLO @ Cmax=2M"] = _burst_cell(
        args.input, "token_burst", "slo-aware", "2M", args.burst_start_s, args.burst_end_s
    )
    cells["ADAPTIVE-SLO (cold-start)"] = _burst_cell(
        args.input, "token_burst", "adaptive-slo", "100k", args.burst_start_s, args.burst_end_s
    )

    path_md = args.out / "token_burst_static_cmax.md"
    path_csv = args.out / "token_burst_static_cmax.csv"
    path_md.write_text(_markdown(cells, args.burst_start_s, args.burst_end_s), encoding="utf-8")
    _write_csv(path_csv, cells)
    _plot(args.out / "token_burst_static_cmax.png", cells)
    (args.out / "token_burst_static_cmax.json").write_text(json.dumps(cells, indent=2), encoding="utf-8")
    print(path_md.read_text())
    print(f"wrote {path_md}")


def _burst_cell(root: Path, scenario: str, policy: str, budget_tag: str, start_s: int, end_s: int) -> dict:
    runs = [
        r
        for r in select_latest(load_summary_runs(root, scenario), ("policy", "budget_tag", "rep"), 1, 5)
        if r["policy"] == policy and (r.get("budget_tag") or "").lower() == budget_tag.lower()
    ]
    if not runs:
        return {"missing": True, "source": f"no {scenario}-{policy}-c{budget_tag} runs"}
    summaries = []
    for run in runs:
        events = load_events(run["run_dir"])
        if not events:
            continue
        t0 = min(e["arrival_ts"] for e in events)
        burst = [e for e in events if start_s <= e["arrival_ts"] - t0 < end_s]
        summaries.append(summarize(burst))
    if not summaries:
        return {"missing": True, "source": f"empty events for {policy}-c{budget_tag}"}
    n = len(summaries)
    return {
        "admit": sum(s["admit_rate"] for s in summaries) / n,
        "goodput": sum(s["effective_slo_goodput"] for s in summaries) / n,
        "cond_slo": sum(s["conditional_slo_attainment"] for s in summaries) / n,
        "p99_ms": sum(s["p99_ttft_ms"] or 0 for s in summaries) / n,
        "throttle": sum(s["throttle_rate"] for s in summaries) / n,
        "reps": n,
        "runs": [r["run"] for r in runs],
        "source": f"new {scenario} {policy} c{budget_tag}",
        "missing": False,
    }


def _markdown(cells: dict[str, dict], start_s: int, end_s: int) -> str:
    lines = [
        "# Token burst: Static-Cmax vs C0 vs Adaptive (cold-start)",
        "",
        f"Burst window `{start_s}–{end_s}s`. NONE and STATIC-SLO@C0 are frozen archive numbers; "
        "STATIC-SLO@Cmax and ADAPTIVE-SLO are new 5-rep cells with Ĉ starting at C0.",
        "",
        "| Cell | Admit | Effective goodput | Conditional SLO | P99 TTFT | Throttle | Source |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, cell in cells.items():
        if cell.get("missing"):
            lines.append(f"| {name} | — | — | — | — | — | {cell.get('source', '')} |")
            continue
        lines.append(
            f"| {name} | {cell['admit']:.3f} | {cell['goodput']:.3f} | {cell['cond_slo']:.3f} | "
            f"{cell['p99_ms']:.0f} ms | {cell['throttle']:.3f} | {cell.get('source', '')} |"
        )
    lines.extend(
        [
            "",
            "If Static-Cmax recovers goodput to ~100% with a slightly worse P99, the reviewer line is: "
            "a large fixed budget recovers goodput here but cannot contract when the provider tightens.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_csv(path: Path, cells: dict[str, dict]) -> None:
    cols = ["cell", "admit", "goodput", "cond_slo", "p99_ms", "throttle", "source"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(cols)
        for name, cell in cells.items():
            writer.writerow(
                [
                    name,
                    cell.get("admit", ""),
                    cell.get("goodput", ""),
                    cell.get("cond_slo", ""),
                    cell.get("p99_ms", ""),
                    cell.get("throttle", ""),
                    cell.get("source", ""),
                ]
            )


def _plot(path: Path, cells: dict[str, dict]) -> None:
    names = [n for n, c in cells.items() if not c.get("missing")]
    if not names:
        return
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    fig.suptitle("Token burst burst-phase: Static-Cmax comparison")
    axes[0].bar(names, [100 * cells[n]["goodput"] for n in names])
    axes[0].set_ylabel("Effective SLO goodput (%)")
    axes[0].set_ylim(0, 100)
    axes[1].bar(names, [cells[n]["p99_ms"] for n in names])
    axes[1].set_ylabel("P99 TTFT (ms)")
    axes[2].bar(names, [100 * cells[n]["throttle"] for n in names])
    axes[2].set_ylabel("Throttle (%)")
    axes[2].set_ylim(0, 100)
    for ax in axes:
        ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
