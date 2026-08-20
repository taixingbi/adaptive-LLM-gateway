# Noisy Neighbor All-Policies Summary

Selection rule: latest run per `(policy, repetition)` for `r1..r5` (based on timestamp in run folder name).

| Policy | Reps | Admit rate | Conditional SLO | Effective SLO Goodput | P99 TTFT (ms) | Throttle rate |
|---|---:|---:|---:|---:|---:|---:|
| `none` | 5 | 1.000 | 0.999 | 0.999 | 562.0 | 0.000 |
| `priority` | 5 | 0.837 | 0.996 | 0.833 | 397.0 | 0.163 |
| `rpm` | 5 | 1.000 | 1.000 | 1.000 | 528.8 | 0.000 |
| `slo-aware` | 5 | 0.867 | 0.977 | 0.847 | 393.9 | 0.133 |
| `token-bucket` | 5 | 0.914 | 0.997 | 0.910 | 450.7 | 0.086 |
| `tpm` | 5 | 0.855 | 0.982 | 0.839 | 578.8 | 0.145 |

## Selected runs (per policy, repetition)

- `none`: r1: noisy_neighbor-none-r1-20260818-202620; r2: noisy_neighbor-none-r2-20260818-203818; r3: noisy_neighbor-none-r3-20260818-205033; r4: noisy_neighbor-none-r4-20260818-210216; r5: noisy_neighbor-none-r5-20260818-211516
- `priority`: r1: noisy_neighbor-priority-r1-20260819-002640; r2: noisy_neighbor-priority-r2-20260819-003838; r3: noisy_neighbor-priority-r3-20260819-005020; r4: noisy_neighbor-priority-r4-20260819-010204; r5: noisy_neighbor-priority-r5-20260819-011348
- `rpm`: r1: noisy_neighbor-rpm-r1-20260818-212715; r2: noisy_neighbor-rpm-r2-20260818-213913; r3: noisy_neighbor-rpm-r3-20260818-215056; r4: noisy_neighbor-rpm-r4-20260818-220239; r5: noisy_neighbor-rpm-r5-20260818-221437
- `slo-aware`: r1: noisy_neighbor-slo-aware-r1-20260819-012547; r2: noisy_neighbor-slo-aware-r2-20260819-013800; r3: noisy_neighbor-slo-aware-r3-20260819-014945; r4: noisy_neighbor-slo-aware-r4-20260819-020142; r5: noisy_neighbor-slo-aware-r5-20260819-021326
- `token-bucket`: r1: noisy_neighbor-token-bucket-r1-20260818-232557; r2: noisy_neighbor-token-bucket-r2-20260818-233856; r3: noisy_neighbor-token-bucket-r3-20260818-235054; r4: noisy_neighbor-token-bucket-r4-20260819-000254; r5: noisy_neighbor-token-bucket-r5-20260819-001440
- `tpm`: r1: noisy_neighbor-tpm-r1-20260818-222621; r2: noisy_neighbor-tpm-r2-20260818-223818; r3: noisy_neighbor-tpm-r3-20260818-225001; r4: noisy_neighbor-tpm-r4-20260818-230145; r5: noisy_neighbor-tpm-r5-20260818-231344
