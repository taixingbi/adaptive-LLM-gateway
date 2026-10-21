#!/usr/bin/env python3
"""Direct Bedrock load that bypasses the gateway (provider-contraction)."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import boto3
import yaml
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = "us.amazon.nova-micro-v1:0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--start-s", type=float, default=0)
    parser.add_argument("--end-s", type=float, default=180)
    parser.add_argument("--run-s", type=float, default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt-class", default="long")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    run_s = float(args.run_s if args.run_s is not None else args.end_s)
    prompt = _prompt(args.prompt_class)
    t0 = time.time()
    stop = threading.Event()
    lock = threading.Lock()
    events: list[dict] = []

    def worker(wid: int) -> None:
        client = boto3.client("bedrock-runtime", region_name=args.region)
        while not stop.is_set():
            elapsed = time.time() - t0
            if elapsed >= run_s:
                return
            if elapsed < args.start_s or elapsed >= args.end_s:
                time.sleep(0.2)
                continue
            start_ts = time.time()
            event = {
                "worker": wid,
                "start_ts": start_ts,
                "elapsed_s": start_ts - t0,
                "model": args.model,
                "bedrock_429": False,
                "bedrock_5xx": False,
                "error": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "ttft_ms": None,
                "e2e_ms": None,
            }
            try:
                response = client.converse_stream(
                    modelId=args.model,
                    messages=[{"role": "user", "content": [{"text": prompt}]}],
                    inferenceConfig={"maxTokens": args.max_tokens},
                )
                first_token_ts = None
                for item in response.get("stream") or []:
                    if "contentBlockDelta" in item and first_token_ts is None:
                        first_token_ts = time.time()
                    elif "metadata" in item:
                        usage = item["metadata"].get("usage") or {}
                        event["input_tokens"] = int(usage.get("inputTokens") or 0)
                        event["output_tokens"] = int(usage.get("outputTokens") or 0)
                finish_ts = time.time()
                event["e2e_ms"] = (finish_ts - start_ts) * 1000
                if first_token_ts is not None:
                    event["ttft_ms"] = (first_token_ts - start_ts) * 1000
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                event["error"] = str(exc)
                event["e2e_ms"] = (time.time() - start_ts) * 1000
                if code in {"ThrottlingException", "TooManyRequestsException", "ServiceQuotaExceededException"}:
                    event["bedrock_429"] = True
                else:
                    event["bedrock_5xx"] = True
            except Exception as exc:  # noqa: BLE001
                event["error"] = str(exc)
                event["e2e_ms"] = (time.time() - start_ts) * 1000
                event["bedrock_5xx"] = True
            with lock:
                events.append(event)
                if args.out:
                    args.out.parent.mkdir(parents=True, exist_ok=True)
                    with args.out.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(event) + "\n")

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(max(args.concurrency, 1))]
    for thread in threads:
        thread.start()
    deadline = t0 + run_s
    try:
        while time.time() < deadline:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    stop.set()
    for thread in threads:
        thread.join(timeout=30)
    n429 = sum(1 for e in events if e.get("bedrock_429"))
    print(json.dumps({"requests": len(events), "bedrock_429": n429, "concurrency": args.concurrency}), flush=True)
    return 0


def _prompt(prompt_class: str) -> str:
    manifest = yaml.safe_load((ROOT / "prompts" / "manifest.yaml").read_text(encoding="utf-8"))
    spec = (manifest.get("prompts") or {}).get(prompt_class) or {}
    path = spec.get("path")
    if path:
        text_path = ROOT / "prompts" / path
        if text_path.exists():
            return text_path.read_text(encoding="utf-8")
    short = ROOT / "prompts" / "short.txt"
    base = short.read_text(encoding="utf-8") if short.exists() else "Reply with one word: ok."
    repeats = {"short": 1, "medium": 8, "long": 32}.get(prompt_class, 8)
    return " ".join([base] * repeats)


if __name__ == "__main__":
    sys.exit(main())
