#!/usr/bin/env python3
"""Plot adaptive controller response from a single run's JSONL events."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from metrics import load_events  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--bin-s", type=float, default=5.0)
    args = parser.parse_args()

    events = load_events(args.run_dir)
    if not events:
        raise SystemExit(f"no events in {args.run_dir}")

    series = bin_trace(events, args.bin_s)
    out = args.out or (args.run_dir / "adaptive_trace.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    _plot(series, out, args.run_dir.name)
    csv_path = out.with_suffix(".csv")
    _write_csv(series, csv_path)
    print(f"wrote {out}")
    print(f"wrote {csv_path}")


def bin_trace(events: list[dict], bin_s: float) -> dict[str, list]:
    t0 = min(e["arrival_ts"] for e in events)
    bins: dict[int, list[dict]] = {}
    for event in events:
        bins.setdefault(int((event["arrival_ts"] - t0) // bin_s), []).append(event)

    xs, offered, tokens, capacity, admit, reject, slo_fail, p99, r429 = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    for b in sorted(bins):
        rows = bins[b]
        n = max(len(rows), 1)
        xs.append(b * bin_s)
        offered.append(len(rows) / bin_s)
        tokens.append(sum(int(e.get("input_tokens") or 0) + int(e.get("output_tokens") or 0) for e in rows) / bin_s)
        caps = [e.get("adaptive_capacity") for e in rows if e.get("adaptive_capacity") is not None]
        capacity.append(sum(float(c) for c in caps) / len(caps) if caps else None)
        admit.append(sum(1 for e in rows if e.get("decision") == "ADMIT") / n)
        reject.append(sum(1 for e in rows if e.get("decision") == "REJECT") / n)
        admitted = [e for e in rows if e.get("decision") == "ADMIT"]
        slo_fail.append(sum(1 for e in admitted if e.get("slo_met") is False) / max(len(admitted), 1))
        ttfts = sorted(e["ttft_ms"] for e in admitted if e.get("ttft_ms") is not None)
        p99.append(ttfts[int(0.99 * (len(ttfts) - 1))] if ttfts else None)
        r429.append(sum(1 for e in rows if e.get("bedrock_429")) / n)
    return {
        "t_s": xs,
        "offered_rps": offered,
        "offered_tokens_s": tokens,
        "adaptive_capacity": capacity,
        "admit_rate": admit,
        "reject_rate": reject,
        "slo_fail_rate": slo_fail,
        "p99_ttft_ms": p99,
        "bedrock_429_rate": r429,
    }


def _plot(series: dict[str, list], out: Path, title: str) -> None:
    fig, axes = plt.subplots(5, 1, figsize=(10, 13), sharex=True)
    fig.suptitle(f"Adaptive response — {title}")
    axes[0].plot(series["t_s"], series["offered_rps"], marker=".", label="req/s")
    ax0b = axes[0].twinx()
    ax0b.plot(series["t_s"], series["offered_tokens_s"], marker=".", color="tab:orange", label="tokens/s")
    axes[0].set_ylabel("Offered req/s")
    ax0b.set_ylabel("Offered tokens/s")
    axes[1].plot(series["t_s"], series["adaptive_capacity"], marker=".")
    axes[1].set_ylabel("Adaptive C_hat")
    axes[2].plot(series["t_s"], [100 * a for a in series["admit_rate"]], marker=".", label="admit")
    axes[2].plot(series["t_s"], [100 * a for a in series["reject_rate"]], marker=".", label="reject")
    axes[2].set_ylabel("Admit / reject (%)")
    axes[2].legend()
    axes[3].plot(series["t_s"], [100 * a for a in series["slo_fail_rate"]], marker=".", label="SLO-fail")
    axes[3].plot(series["t_s"], [100 * a for a in series["bedrock_429_rate"]], marker=".", label="429")
    axes[3].set_ylabel("SLO-fail / 429 (%)")
    axes[3].legend()
    axes[4].plot(series["t_s"], series["p99_ttft_ms"], marker=".")
    axes[4].set_ylabel("P99 TTFT (ms)")
    axes[4].set_xlabel("Time (s)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _write_csv(series: dict[str, list], path: Path) -> None:
    keys = list(series)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(keys)
        for i in range(len(series["t_s"])):
            writer.writerow([series[k][i] for k in keys])


if __name__ == "__main__":
    main()
