# Token Burst All-Policies Summary (full run)

Selection rule: latest run per `(policy, repetition)` for `r1..r5`.

| Policy | Reps | Admit | Conditional SLO | Effective SLO Goodput | P95 TTFT (ms) | P99 TTFT (ms) | Throttle |
|---|---:|---:|---:|---:|---:|---:|---:|
| `none` | 5 | 1.000 | 1.000 | 1.000 | 451.0 | 550.3 | 0.000 |
| `priority` | 5 | 0.371 | 0.948 | 0.352 | 353.2 | 421.3 | 0.629 |
| `rpm` | 5 | 1.000 | 1.000 | 1.000 | 415.2 | 507.4 | 0.000 |
| `slo-aware` | 5 | 0.285 | 0.888 | 0.253 | 342.3 | 393.9 | 0.715 |
| `token-bucket` | 5 | 0.437 | 0.899 | 0.393 | 428.0 | 479.0 | 0.563 |
| `tpm` | 5 | 0.331 | 0.922 | 0.305 | 390.7 | 472.0 | 0.669 |

## Selected runs

- `none`: r1: token_burst-none-r1-20260819-204840; r2: token_burst-none-r2-20260819-205738; r3: token_burst-none-r3-20260819-210751; r4: token_burst-none-r4-20260819-212053; r5: token_burst-none-r5-20260819-213121
- `priority`: r1: token_burst-priority-r1-20260820-001317; r2: token_burst-priority-r2-20260820-002330; r3: token_burst-priority-r3-20260820-003228; r4: token_burst-priority-r4-20260820-004108; r5: token_burst-priority-r5-20260820-005005
- `rpm`: r1: token_burst-rpm-r1-20260819-214133; r2: token_burst-rpm-r2-20260819-215202; r3: token_burst-rpm-r3-20260819-220315; r4: token_burst-rpm-r4-20260819-221429; r5: token_burst-rpm-r5-20260819-222441
- `slo-aware`: r1: token_burst-slo-aware-r1-20260820-005917; r2: token_burst-slo-aware-r2-20260820-010813; r3: token_burst-slo-aware-r3-20260820-011724; r4: token_burst-slo-aware-r4-20260820-012606; r5: token_burst-slo-aware-r5-20260820-013503
- `token-bucket`: r1: token_burst-token-bucket-r1-20260819-232459; r2: token_burst-token-bucket-r2-20260819-233340; r3: token_burst-token-bucket-r3-20260819-234353; r4: token_burst-token-bucket-r4-20260819-235405; r5: token_burst-token-bucket-r5-20260820-000434
- `tpm`: r1: token_burst-tpm-r1-20260819-223640; r2: token_burst-tpm-r2-20260819-224910; r3: token_burst-tpm-r3-20260819-225822; r4: token_burst-tpm-r4-20260819-230719; r5: token_burst-tpm-r5-20260819-231617
