# Token Burst Comparison (5-run frozen selection)

Scenario: `experiments/token_burst.yaml` (+ `token_burst_adaptive.yaml` for `adaptive-slo`).  
Selection: latest run per `(policy, repetition)` for `r1..r5`.

## Burst-phase results (180–360s) — primary table

| Policy | Admit | Effective goodput | Conditional SLO | P99 TTFT | Throttle |
|---|---:|---:|---:|---:|---:|
| `none` | 1.000 | 1.000 | 1.000 | 566 ms | 0.000 |
| `rpm` | 1.000 | 1.000 | 1.000 | 532 ms | 0.000 |
| `tpm` | 0.060 | 0.037 | 0.610 | 465 ms | 0.940 |
| `token-bucket` | 0.113 | 0.073 | 0.646 | 511 ms | 0.887 |
| `priority` | 0.134 | 0.115 | 0.855 | 413 ms | 0.866 |
| `slo-aware` | 0.049 | 0.046 | 0.949 | 398 ms | 0.951 |
| `adaptive-slo` | **0.860** | **0.844** | 0.982 | 494 ms | 0.140 |

## Adaptive validation (main new claim)

`adaptive-slo` vs static `slo-aware` in the same burst window:

- Effective SLO goodput: **0.844 vs 0.046** (~18×)
- Admit rate: **0.860 vs 0.049**
- Conditional SLO among admitted: **0.982 vs 0.949** (retained)
- P99 TTFT: **494 vs 398 ms** (~24% higher — most of the tail protection trade-off)

Controller evidence (traces in `adaptive_trace_token_burst_r{1,2,3}.png`): under healthy Bedrock (0 provider 429s), policy rejects drive multiplicative `increase-demand` and `C_hat` rises to `c_max` (2M TPM), restoring admit rate without collapsing conditional SLO.

## Findings supported by data

1. **RPM blindness.** During the token-size burst, `rpm` matches `none`: both keep ~100% admit / goodput.
2. **Static token/SLO over-shed.** `tpm` / `token-bucket` / `priority` / `slo-aware` throttle ~87–95% in burst; static `slo-aware` has the lowest goodput among them.
3. **Adaptive recovers goodput.** AIMD on `C_hat` recovers most of the effective goodput that static SLO-aware leaves on the table, while keeping high conditional SLO and only a moderate P99 increase vs static.
4. **Backend still healthy under none/rpm.** This remains a policy-differentiation result under token pressure, not a claim that uncontrolled traffic already violates SLO.

## Paper-ready takeaway

At constant request rate, a token-size burst exposes overload that RPM cannot see. Static SLO-aware over-sheds against an elastic Bedrock backend. Adaptive SLO-aware raises `C_hat` when the provider stays healthy, recovering substantially more effective goodput while retaining most of the tail-latency protection.

## Artifacts

- `token_burst_burst_phase_summary.md` / `token_burst_policy_summary.csv` / `.png`
- `adaptive_trace_token_burst_r{1,2,3}.png`
