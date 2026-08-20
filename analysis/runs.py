"""Latest-run selection and metric aggregation shared by paper plot scripts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean, pstdev

import matplotlib.pyplot as plt

POLICY_METRICS = [
    "admit_rate",
    "conditional_slo_attainment",
    "effective_slo_goodput",
    "p95_ttft_ms",
    "p99_ttft_ms",
    "throttle_rate",
]


def load_summary_runs(root: Path, scenario: str) -> list[dict]:
    pattern = re.compile(rf"{re.escape(scenario)}-([a-z\-]+?)(?:-(\d+)pct)?-r(\d+)-")
    rows: list[dict] = []
    for file in root.glob(f"{scenario}-*/summary.json"):
        match = pattern.match(file.parent.name)
        if not match:
            continue
        rows.append(
            {
                "policy": match.group(1),
                "load_pct": int(match.group(2)) if match.group(2) is not None else None,
                "rep": int(match.group(3)),
                "summary": json.loads(file.read_text(encoding="utf-8")),
                "run": file.parent.name,
                "run_dir": file.parent,
            }
        )
    return rows


def select_latest(rows: list[dict], keys: tuple[str, ...], rep_min: int, rep_max: int) -> list[dict]:
    latest: dict[tuple, dict] = {}
    for row in rows:
        if row["rep"] < rep_min or row["rep"] > rep_max:
            continue
        key = tuple(row.get(k) for k in keys)
        prev = latest.get(key)
        if prev is None or row["run"] > prev["run"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda r: tuple(r.get(k) if r.get(k) is not None else 0 for k in keys))


def metric_value(summary: dict, name: str) -> float | None:
    if name == "effective_slo_goodput":
        if summary.get("effective_slo_goodput") is not None:
            return summary["effective_slo_goodput"]
        if summary.get("slo_goodput") is not None:
            return summary["slo_goodput"]
        admit, slo = summary.get("admit_rate"), summary.get("slo_attainment")
        if admit is not None and slo is not None:
            return admit * slo
        return None
    if name == "conditional_slo_attainment":
        value = summary.get("conditional_slo_attainment")
        return summary.get("slo_attainment") if value is None else value
    return summary.get(name)


def aggregate(rows: list[dict], group_key: str, metrics: list[str] | None = None) -> list[dict]:
    metrics = metrics or POLICY_METRICS
    groups: dict = {}
    for row in rows:
        groups.setdefault(row[group_key], []).append(row)
    out: list[dict] = []
    for key in sorted(groups, key=lambda k: (k is None, k)):
        group = groups[key]
        summaries = [r["summary"] for r in group]
        agg = {group_key: key, "repetitions": len(summaries)}
        for metric in metrics:
            col = [v for v in (metric_value(s, metric) for s in summaries) if v is not None]
            agg[f"{metric}_mean"] = mean(col) if col else None
            agg[f"{metric}_std"] = pstdev(col) if len(col) > 1 else 0.0
        agg["selected_runs"] = [r["run"] for r in sorted(group, key=lambda x: x["rep"])]
        out.append(agg)
    return out


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(str(row.get(h, "")) for h in columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_selected_runs_md(
    lines: list[str],
    selected: list[dict],
    group_key: str,
    heading: str = "## Selected runs",
) -> None:
    lines.extend(["", heading, ""])
    by_group: dict = {}
    for row in selected:
        by_group.setdefault(row[group_key], []).append(row)
    for key in sorted(by_group, key=lambda k: (k is None, k)):
        ordered = sorted(by_group[key], key=lambda r: r["rep"])
        parts = [f"r{r['rep']}: {r['run']}" for r in ordered]
        lines.append(f"- `{key}`: " + "; ".join(parts))


def plot_triple(
    path: Path,
    xs: list,
    *,
    goodput: list[float],
    p99: list[float],
    throttle: list[float],
    title: str,
    kind: str = "bar",
    xlabel: str | None = None,
    goodput_err: list[float] | None = None,
    p99_err: list[float] | None = None,
    throttle_err: list[float] | None = None,
    rotate_x: bool = True,
) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    fig.suptitle(title)
    series = [
        (goodput, goodput_err, "Effective SLO goodput (%)", True),
        (p99, p99_err, "P99 TTFT (ms)", False),
        (throttle, throttle_err, "Throttle rate (%)", True),
    ]
    for ax, (values, err, ylabel, pct) in zip(axes, series):
        y = [100 * v if pct else v for v in values]
        yerr = None if err is None else [100 * e if pct else e for e in err]
        if kind == "bar":
            ax.bar(xs, y, yerr=yerr, capsize=3)
        else:
            ax.plot(xs, y, marker="o")
        ax.set_ylabel(ylabel)
        if pct:
            ax.set_ylim(0, 100)
        if xlabel:
            ax.set_xlabel(xlabel)
        if rotate_x:
            ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def policy_csv_columns(include_p95: bool = False) -> list[str]:
    cols = [
        "policy",
        "repetitions",
        "admit_rate_mean",
        "admit_rate_std",
        "conditional_slo_attainment_mean",
        "conditional_slo_attainment_std",
        "effective_slo_goodput_mean",
        "effective_slo_goodput_std",
    ]
    if include_p95:
        cols += ["p95_ttft_ms_mean", "p95_ttft_ms_std"]
    cols += [
        "p99_ttft_ms_mean",
        "p99_ttft_ms_std",
        "throttle_rate_mean",
        "throttle_rate_std",
    ]
    return cols
