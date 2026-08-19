# Noisy Neighbor Pilot Comparison

This note compares the noisy-neighbor experiment under `none` vs `slo-aware`.

## Scope

- Backend: Bedrock Nova Micro (`us.amazon.nova-micro-v1:0`)
- Scenario: `experiments/noisy_neighbor.yaml`
- Duration per run: 540s
- Reported metrics exclude victim tenant `tenant-007` (per scenario config)

## Runs Included

- `none`: `r1` to `r5` full 100-tenant runs
- `slo-aware`: 20260819 `r1` to `r5` full 100-tenant runs

## Aggregated Results (latest r1-r5 selection)

| Policy | Admit rate | Throttle rate | Conditional SLO | SLO goodput | p99 TTFT |
|---|---:|---:|---:|---:|---:|
| `none` | 1.000 | 0.000 | ~0.999 | ~0.999 | ~562 ms |
| `slo-aware` | 0.867 ± 0.023 | 0.133 ± 0.023 | 0.977 ± 0.003 | ~0.847 | 394 ± 13 ms |

## Interpretation

- `slo-aware` reduces p99 TTFT from ~562 ms to ~394 ms (about 30% lower tail latency).
- This improvement is achieved by proactive shedding (~13% throttling on average).
- Priority behavior matches design intent: P1 admission remains high but not perfect (~98.5% pooled across the selected 5 runs), while lower tiers absorb most throttling.

## Paper-ready Takeaway

Under the current noisy-neighbor workload with a real Bedrock backend, the SLO-aware controller primarily shows a latency-vs-admission tradeoff: it lowers p99 TTFT by roughly 30% relative to no admission control at the cost of approximately 13% request shedding. This pilot does not yet demonstrate improved effective SLO success versus a baseline that is already near-saturated but still within SLO.
