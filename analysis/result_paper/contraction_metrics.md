# Provider contraction / recovery

Background pressure window: `240–480s`. Ĉ reset to C0 before each rep.

| Metric | Mean | Std | n |
|---|---:|---:|---:|
| Pre-pressure Ĉ | 80238.162 | 27175.688 | 5 |
| T_contract to −20% (s) | 50.057 | 38.405 | 4 |
| T_contract to −50% (s) | 36.109 | 0.000 | 1 |
| T_recover to 90% (s) | 50.000 | 26.220 | 4 |
| Contraction SLO-fail rate | 0.308 | 0.059 | 5 |
| Contraction 429 rate | 0.015 | 0.005 | 5 |
| Contraction effective goodput | 0.408 | 0.071 | 5 |
| Contraction admit rate | 0.593 | 0.110 | 5 |
| Contraction P99 TTFT (ms) | 7275.573 | 2153.929 | 5 |

## Per-rep

- r1: `provider_contraction-adaptive-slo-c100k-r1-20261021-171404` Ĉ_pre=133001.9074889868
- r2: `provider_contraction-adaptive-slo-c100k-r2-20261021-172948` Ĉ_pre=78310.24666666667
- r3: `provider_contraction-adaptive-slo-c100k-r3-20261021-174153` Ĉ_pre=66433.83812010444
- r4: `provider_contraction-adaptive-slo-c100k-r4-20261021-175357` Ĉ_pre=57938.57323232323
- r5: `provider_contraction-adaptive-slo-c100k-r5-20261021-180601` Ĉ_pre=65506.243055555555
