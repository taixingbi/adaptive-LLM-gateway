from __future__ import annotations

from pathlib import Path

SENTENCE = "The queue depth is rising and latency SLOs are at risk. "
SEED = "Summarize the following enterprise operations note in one sentence. "

# Placeholder token counts until scripts/count_tokens.py stamps Bedrock CountTokens.
# ~4 characters per token is a planning estimate, not a model tokenizer.
CLASSES = {
    "short": {"target_tokens": 250, "max_tokens": 64, "input_tokens": 284},
    "medium": {"target_tokens": 2000, "max_tokens": 256, "input_tokens": 1942},
    "long": {"target_tokens": 8000, "max_tokens": 1024, "input_tokens": 8217},
}


def prompt_for(target_tokens: int) -> str:
    # English prose ≈ 4 chars/token. Overshoot slightly so CountTokens can trim later.
    repeats = max(1, (target_tokens * 4 - len(SEED)) // len(SENTENCE))
    return SEED + SENTENCE * repeats


def main() -> None:
    root = Path(__file__).parent
    meta_lines = ["# Known token demand used by Locust. Update after CountTokens.", "prompts:"]
    for name, spec in CLASSES.items():
        text = prompt_for(spec["target_tokens"])
        path = root / f"{name}.txt"
        path.write_text(text, encoding="utf-8")
        meta_lines.append(f"  {name}:")
        meta_lines.append(f"    path: {name}.txt")
        meta_lines.append(f"    input_tokens: {spec['input_tokens']}")
        meta_lines.append(f"    max_tokens: {spec['max_tokens']}")
        print(f"wrote {path} chars={len(text)}")
    (root / "manifest.yaml").write_text("\n".join(meta_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
