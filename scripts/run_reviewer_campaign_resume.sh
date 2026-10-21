#!/usr/bin/env bash
# Resume after abort: Exp2 adaptive r5, then Exp3 × 5, then plots.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
export PYTHONUNBUFFERED=1
LOG="${ROOT}/analysis/out/reviewer_campaign_resume.log"
mkdir -p "${ROOT}/analysis/out" "${ROOT}/analysis/result_paper"

run() {
  echo "==== $(date) $*" | tee -a "$LOG"
  "$PY" "$@" 2>&1 | tee -a "$LOG"
}

run scripts/run_experiment.py experiments/token_burst.yaml \
  --policy adaptive-slo --skip-deploy --repetitions 1 --rep-start 5 --platform-tpm-budget 100000 --reset-adaptive

run scripts/run_experiment.py experiments/provider_contraction.yaml \
  --policy adaptive-slo --deploy --repetitions 5 --platform-tpm-budget 100000 --reset-adaptive \
  --background-concurrency 8

echo "==== $(date) plots" | tee -a "$LOG"
for d in "${ROOT}"/analysis/out/token_burst_coldstart-adaptive-slo-c100k-r*; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  [[ "$name" == *20261021-111453 ]] && continue
  rep="$(echo "$name" | python3 -c 'import re,sys; m=re.search(r"-r(\d+)-", sys.stdin.read()); print(m.group(1) if m else "x")')"
  "$PY" analysis/plot_adaptive_trace.py "$d" --out "${ROOT}/analysis/result_paper/adaptive_trace_coldstart_r${rep}.png"
done

"$PY" analysis/compare_static_cmax.py --input "${ROOT}/analysis/out" --out "${ROOT}/analysis/result_paper"
"$PY" analysis/plot_contraction.py --input "${ROOT}/analysis/out" --out "${ROOT}/analysis/result_paper"

echo "==== $(date) campaign resume done" | tee -a "$LOG"
