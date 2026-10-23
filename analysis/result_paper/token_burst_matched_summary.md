# Token burst: matched-window Table IV

Burst window `120–300s` from each run’s `min(arrival_ts)`. Each repetition is summarized first; cells report mean ± sample SD (`statistics.stdev`, n−1). Requests are not pooled across repetitions.

Adaptive-cold reuses the existing `token_burst_coldstart` health-fix runs (stamp ≥ 20261021-1938). `token_burst_static_cmax.md` remains the unmatched 180–360s archive.

| Cell | Admit | Effective goodput | Conditional SLO | P99 TTFT | Throttle | Bedrock 429 |
|---|---:|---:|---:|---:|---:|---:|
| NONE | 1.000±0.000 | 1.000±0.000 | 1.000±0.000 | 583±84 ms | 0.000±0.000 | 0.000±0.000 |
| STATIC-SLO @ C0 | 0.048±0.006 | 0.045±0.003 | 0.942±0.064 | 531±54 ms | 0.952±0.006 | 0.000±0.000 |
| STATIC-SLO @ Cmax | 0.821±0.056 | 0.805±0.054 | 0.980±0.007 | 514±42 ms | 0.179±0.056 | 0.000±0.000 |
| Adaptive-cold | 0.624±0.080 | 0.519±0.068 | 0.831±0.012 | 516±37 ms | 0.376±0.080 | 0.000±0.000 |

## Selected runs

- `Adaptive-cold`: r1: token_burst_coldstart-adaptive-slo-c100k-r1-20261021-193851; r2: token_burst_coldstart-adaptive-slo-c100k-r2-20261021-194933; r3: token_burst_coldstart-adaptive-slo-c100k-r3-20261021-195736; r4: token_burst_coldstart-adaptive-slo-c100k-r4-20261021-200544; r5: token_burst_coldstart-adaptive-slo-c100k-r5-20261021-201348
- `NONE`: r1: token_burst_coldstart_c100k-none-c100k-r1-20261022-185849; r2: token_burst_coldstart_c100k-none-c100k-r2-20261022-190930; r3: token_burst_coldstart_c100k-none-c100k-r3-20261022-191732; r4: token_burst_coldstart_c100k-none-c100k-r4-20261022-192535; r5: token_burst_coldstart_c100k-none-c100k-r5-20261022-193337
- `STATIC-SLO @ C0`: r1: token_burst_coldstart_c100k-slo-aware-c100k-r1-20261022-194139; r2: token_burst_coldstart_c100k-slo-aware-c100k-r2-20261022-195655; r3: token_burst_coldstart_c100k-slo-aware-c100k-r3-20261022-200458; r4: token_burst_coldstart_c100k-slo-aware-c100k-r4-20261022-201301; r5: token_burst_coldstart_c100k-slo-aware-c100k-r5-20261022-202104
- `STATIC-SLO @ Cmax`: r1: token_burst_coldstart_c2m-slo-aware-c2M-r1-20261022-202910; r2: token_burst_coldstart_c2m-slo-aware-c2M-r2-20261022-203953; r3: token_burst_coldstart_c2m-slo-aware-c2M-r3-20261022-204755; r4: token_burst_coldstart_c2m-slo-aware-c2M-r4-20261022-205558; r5: token_burst_coldstart_c2m-slo-aware-c2M-r5-20261022-210401
