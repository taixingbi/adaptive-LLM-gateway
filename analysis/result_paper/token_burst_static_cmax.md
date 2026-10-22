# Token burst: Static-Cmax vs C0 vs Adaptive (cold-start)

NONE and STATIC-SLO@C0 are frozen archive numbers (burst 180–360s on `token_burst.yaml`).
STATIC-SLO@Cmax is the new 5-rep cell on the same 360s YAML.
ADAPTIVE-SLO is the **reset-to-C0** 5-rep cell on `token_burst_coldstart.yaml` (burst 120–300s) after the provider-health fix.

Do not headline the archived warm-state 0.844 / 18×.

| Cell | Admit | Effective goodput | Conditional SLO | P99 TTFT | Throttle | Source |
|---|---:|---:|---:|---:|---:|---|
| NONE | 1.000 | 1.000 | 1.000 | 566 ms | 0.000 | frozen token_burst none |
| STATIC-SLO @ C0=100k | 0.049 | 0.046 | 0.949 | 398 ms | 0.951 | frozen token_burst slo-aware |
| STATIC-SLO @ Cmax=2M | 0.851 | 0.832 | 0.978 | 854 ms | 0.149 | new token_burst slo-aware c2M |
| ADAPTIVE-SLO (cold-start) | 0.624 | 0.519 | 0.831 | 516 ms | 0.376 | reset Ĉ=C0; burst 120–300s |

Ĉ on every adaptive rep: **100k → 2M**. Burst goodput 0.519 is ~11× static-C0 (0.046) and still below static-Cmax (0.832) because the climb happens *during* the burst window.

A large fixed budget recovers more goodput here but cannot contract when the provider tightens (see `contraction_metrics.md`).
