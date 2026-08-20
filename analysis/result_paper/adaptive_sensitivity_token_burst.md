# Adaptive AIMD Sensitivity (token burst, 1 rep each)

Burst window 180–360s. Baseline is the 5-rep mean for default `α=0.15, β=0.7, window=15s`.
Static `slo-aware` reference: admit 0.049, goodput 0.046, P99 398 ms.

| Config | Admit | Effective goodput | Cond. SLO | P99 TTFT |
|---|---:|---:|---:|---:|
| baseline α0.15 β0.7 w15 (5-rep mean) | 0.860 | 0.844 | 0.982 | 494 |
| α0.05 β0.7 w15 | 0.848 | 0.833 | 0.982 | 476 |
| α0.30 β0.7 w15 | 0.826 | 0.808 | 0.979 | 557 |
| α0.15 β0.5 w15 | 0.932 | 0.921 | 0.989 | 535 |
| α0.15 β0.7 w5 | 0.831 | 0.806 | 0.970 | 505 |
| α0.15 β0.7 w30 | 0.883 | 0.866 | 0.981 | 552 |

## Takeaway

Across this small ablation, burst-phase effective goodput stays in ~0.81–0.92 — always ≫ static 0.046. The main Adaptive claim is not a single lucky `(α,β,window)` setting. Mild variation exists (faster decrease β=0.5 admits more; smaller α / shorter window a bit more conservative), but order-of-magnitude recovery vs static holds.
