#!/usr/bin/env python3
"""Stamp loadgen/prompts/manifest.yaml with Bedrock CountTokens. Offline only."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "loadgen" / "prompts" / "manifest.yaml"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="us.amazon.nova-micro-v1:0")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    client = boto3.client("bedrock-runtime", region_name=args.region)
    text = MANIFEST.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        path = match.group(2)
        max_tokens = match.group(3)
        prompt = (ROOT / "loadgen" / "prompts" / path).read_text(encoding="utf-8")
        response = client.count_tokens(
            modelId=args.model_id,
            input={"converse": {"messages": [{"role": "user", "content": [{"text": prompt}]}]}},
        )
        tokens = int(response["inputTokens"])
        print(f"{name}: {tokens} tokens")
        return f"  {name}:\n    path: {path}\n    input_tokens: {tokens}\n    max_tokens: {max_tokens}"

    updated = re.sub(
        r"  (\w+):\n    path: (\S+)\n    input_tokens: \d+\n    max_tokens: (\d+)",
        replace,
        text,
    )
    MANIFEST.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
