# Token burst: Static-Cmax vs C0 vs Adaptive (cold-start)

Burst window `180–360s`. NONE and STATIC-SLO@C0 are frozen archive numbers; STATIC-SLO@Cmax and ADAPTIVE-SLO are new 5-rep cells with Ĉ starting at C0.

| Cell | Admit | Effective goodput | Conditional SLO | P99 TTFT | Throttle | Source |
|---|---:|---:|---:|---:|---:|---|
| NONE | 1.000 | 1.000 | 1.000 | 566 ms | 0.000 | frozen token_burst none |
| STATIC-SLO @ C0=100k | 0.049 | 0.046 | 0.949 | 398 ms | 0.951 | frozen token_burst slo-aware |
| STATIC-SLO @ Cmax=2M | 0.851 | 0.832 | 0.978 | 854 ms | 0.149 | new token_burst slo-aware c2M |
| ADAPTIVE-SLO (cold-start) | 0.119 | 0.102 | 0.876 | 566 ms | 0.881 | new token_burst adaptive-slo c100k |

If Static-Cmax recovers goodput to ~100% with a slightly worse P99, the reviewer line is: a large fixed budget recovers goodput here but cannot contract when the provider tightens.
