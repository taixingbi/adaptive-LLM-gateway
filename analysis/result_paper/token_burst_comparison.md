# Token Burst Comparison (5-run frozen selection)

Scenario: `experiments/token_burst.yaml` — fixed ~500 RPM, prompt switches short → long at 180s.  
Selection: latest run per `(policy, repetition)` for `r1..r5`.

## Burst-phase results (180–360s) — primary table

| Policy | Admit | Effective goodput | Conditional SLO | P99 TTFT | Throttle |
|---|---:|---:|---:|---:|---:|
| `none` | 1.000 ± 0.000 | 1.000 ± 0.000 | 1.000 ± 0.000 | 566 ± 23 ms | 0.000 |
| `rpm` | 1.000 ± 0.000 | 1.000 ± 0.001 | 1.000 ± 0.001 | 532 ± 15 ms | 0.000 |
| `tpm` | 0.060 ± 0.008 | 0.037 ± 0.009 | 0.610 ± 0.078 | 465 ± 16 ms | 0.940 |
| `token-bucket` | 0.113 ± 0.001 | 0.073 ± 0.005 | 0.646 ± 0.045 | 511 ± 30 ms | 0.887 |
| `priority` | 0.134 ± 0.003 | 0.115 ± 0.010 | 0.855 ± 0.064 | 413 ± 15 ms | 0.866 |
| `slo-aware` | 0.049 ± 0.005 | 0.046 ± 0.004 | **0.949 ± 0.029** | 398 ± 21 ms | 0.951 |

## Findings supported by data

1. **RPM blindness.** During the token-size burst, `rpm` matches `none`: both keep ~100% admit and ~100% effective goodput. Request-rate limiters do not react to token-size pressure.
2. **Token-aware shedding.** `tpm`, `token-bucket`, `priority`, and `slo-aware` all shed heavily in burst (~87–95% throttle).
3. **Conditional SLO vs goodput tradeoff.** Among shedding policies, `slo-aware` admits the fewest requests (~4.9%) but preserves the highest conditional SLO among admitted (~94.9%). `token-bucket` admits more (~11.3%) but conditional SLO among admitted is only ~64.6%.
4. **Backend still healthy under none/rpm.** On Nova Micro in this workload, `none`/`rpm` remain at ~100% effective goodput during burst — so this experiment demonstrates **policy differentiation under token pressure**, not that uncontrolled traffic already violates SLO.

## Paper-ready takeaway (honest)

At constant request rate, a token-size burst exposes overload that RPM-based controls cannot detect. Token-aware admission policies shed load; among them, SLO-aware admission trades lower burst-phase goodput for substantially higher conditional SLO on the requests it does admit.

## Full-run aggregates

See `token_burst_all_policies_summary.md` (includes the short-prompt first half). Prefer burst-phase tables for the main claim.

## Artifacts

- `token_burst_burst_phase_summary.md` / CSV via `token_burst_policy_summary.csv` (full-run means)
- `token_burst_policy_summary.png` (burst-phase bars)
- Selected run IDs listed in the summary markdown files
