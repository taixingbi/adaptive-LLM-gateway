# Provider contraction / recovery

Background pressure window: `360–600s`. Ĉ reset to C0 before each rep.

| Metric | Mean | Std | n |
|---|---:|---:|---:|
| Pre-pressure Ĉ | 1949140.411 | 49695.099 | 5 |
| T_contract to −20% (s) | 21.750 | 10.316 | 5 |
| T_contract to −50% (s) | 73.731 | 17.233 | 4 |
| T_recover to 90% (s) | 143.750 | 111.376 | 4 |
| Contraction SLO-fail rate | 0.127 | 0.018 | 5 |
| Contraction 429 rate | 0.026 | 0.010 | 5 |
| Contraction effective goodput | 0.873 | 0.018 | 5 |
| Contraction admit rate | 1.000 | 0.000 | 5 |
| Contraction P99 TTFT (ms) | 7155.732 | 1658.437 | 5 |

## Per-rep

- r1: `provider_contraction-adaptive-slo-c100k-r1-20261021-202155` Ĉ_pre=1864539.1270491802
- r2: `provider_contraction-adaptive-slo-c100k-r2-20261021-204428` Ĉ_pre=1973411.3235294118
- r3: `provider_contraction-adaptive-slo-c100k-r3-20261021-205934` Ĉ_pre=1922490.9788135593
- r4: `provider_contraction-adaptive-slo-c100k-r4-20261021-211440` Ĉ_pre=2000000.0
- r5: `provider_contraction-adaptive-slo-c100k-r5-20261021-212947` Ĉ_pre=1985260.625
