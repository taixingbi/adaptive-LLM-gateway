#!/usr/bin/env bash
# Small AIMD sensitivity on token_burst (1 rep each; baseline already has 5 reps).
# Configs: α ∈ {0.05,0.30}, β=0.5, window ∈ {5,30}; default α=0.15 β=0.7 w=15 is baseline.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy || true
export NO_PROXY='*'
LOG="analysis/out/logs/adaptive_sensitivity_$(date +%Y%m%d-%H%M%S).log"
mkdir -p analysis/out/logs
echo "$LOG" > analysis/out/logs/adaptive_sensitivity.latest
exec > >(tee -a "$LOG") 2>&1

YAML=experiments/token_burst_adaptive.yaml
PY=.venv/bin/python

run_one() {
  local a="$1" b="$2" w="$3"
  echo "==> sensitivity alpha=$a beta=$b window=$w"
  "$PY" -u scripts/run_experiment.py "$YAML" \
    --policy adaptive-slo --repetitions 1 --deploy \
    --adaptive-alpha "$a" --adaptive-beta "$b" --adaptive-window-s "$w"
}

# α ablation (β,w fixed at defaults)
run_one 0.05 0.7 15
run_one 0.30 0.7 15
# β ablation
run_one 0.15 0.5 15
# window ablation
run_one 0.15 0.7 5
run_one 0.15 0.7 30

echo "SENSITIVITY_DONE"
