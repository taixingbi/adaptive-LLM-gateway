#!/usr/bin/env python3
"""Plot adaptive controller response from a single run's JSONL events."""

from __future__ import annotations

import argparse
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

    t0 = min(e["arrival_ts"] for e in events)
    bins: dict[int, list[dict]] = {}
    for e in events:
        b = int((e["arrival_ts"] - t0) // args.bin_s)
        bins.setdefault(b, []).append(e)

    xs, offered, capacity, admit, p99, r429 = [], [], [], [], [], []
    for b in sorted(bins):
        rows = bins[b]
        xs.append(b * args.bin_s)
        offered.append(len(rows) / args.bin_s)
        caps = [e.get("adaptive_capacity") for e in rows if e.get("adaptive_capacity") is not None]
        capacity.append(sum(caps) / len(caps) if caps else None)
        admit.append(sum(1 for e in rows if e.get("decision") == "ADMIT") / max(len(rows), 1))
        ttfts = sorted(e["ttft_ms"] for e in rows if e.get("decision") == "ADMIT" and e.get("ttft_ms") is not None)
        p99.append(ttfts[int(0.99 * (len(ttfts) - 1))] if ttfts else None)
        r429.append(sum(1 for e in rows if e.get("bedrock_429")) / max(len(rows), 1))

    out = args.out or (args.run_dir / "adaptive_trace.png")
    fig, axes = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
    fig.suptitle(f"Adaptive response — {args.run_dir.name}")
    axes[0].plot(xs, offered, marker=".")
    axes[0].set_ylabel("Offered req/s")
    axes[1].plot(xs, capacity, marker=".")
    axes[1].set_ylabel("Adaptive C_hat")
    axes[2].plot(xs, [100 * a for a in admit], marker=".")
    axes[2].set_ylabel("Admit rate (%)")
    axes[3].plot(xs, p99, marker=".", label="P99 TTFT")
    axes[3].plot(xs, [1000 * r for r in r429], marker=".", label="429 rate ×1000")
    axes[3].set_ylabel("TTFT / 429")
    axes[3].set_xlabel("Time (s)")
    axes[3].legend()
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
