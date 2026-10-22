#!/usr/bin/env bash
# After the provider-health fix: cold-start ×5, then high→contract→recover ×5.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
export PYTHONUNBUFFERED=1
LOG="${ROOT}/analysis/out/controller_rerun.log"
mkdir -p "${ROOT}/analysis/out" "${ROOT}/analysis/result_paper"

run() {
  echo "==== $(date) $*" | tee -a "$LOG"
  "$PY" "$@" 2>&1 | tee -a "$LOG"
}

run scripts/run_experiment.py experiments/token_burst_coldstart.yaml \
  --policy adaptive-slo --deploy --repetitions 5 --platform-tpm-budget 100000 --reset-adaptive

run scripts/run_experiment.py experiments/provider_contraction.yaml \
  --policy adaptive-slo --deploy --repetitions 5 --platform-tpm-budget 100000 --reset-adaptive \
  --background-concurrency 8

echo "==== $(date) plots" | tee -a "$LOG"
"$PY" - <<'PY'
from pathlib import Path
import re, subprocess, sys
root = Path("analysis/out")
out = Path("analysis/result_paper")
for d in sorted(p for p in root.glob("token_burst_coldstart-adaptive-slo-c100k-r*-2026102*") if p.is_dir()):
    m = re.search(r"-r(\d+)-", d.name)
    if not m:
        continue
    dest = out / f"adaptive_trace_coldstart_r{m.group(1)}.png"
    subprocess.check_call([sys.executable, "analysis/plot_adaptive_trace.py", str(d), "--out", str(dest)])
PY
"$PY" analysis/compare_static_cmax.py --input analysis/out --out analysis/result_paper
"$PY" analysis/plot_contraction.py --input analysis/out --out analysis/result_paper --pressure-start-s 360 --pressure-end-s 600
echo "==== $(date) controller rerun done" | tee -a "$LOG"
