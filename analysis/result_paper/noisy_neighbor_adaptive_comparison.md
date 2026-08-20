# Noisy Neighbor: Adaptive vs Static SLO-aware

Metrics exclude victim `tenant-007`. Selection: latest `r1..r5` per policy.

## Overall (non-victim)

| Policy | Reps | Admit | Cond. SLO | Effective goodput | P99 TTFT | Throttle |
|---|---:|---:|---:|---:|---:|---:|
| `adaptive-slo` | 5 | 1.000 ± 0.000 | 0.997 ± 0.003 | 0.997 ± 0.003 | 624 ± 88 | 0.000 ± 0.000 |
| `slo-aware` | 5 | 0.867 ± 0.023 | 0.977 ± 0.003 | 0.847 ± 0.024 | 394 ± 13 | 0.133 ± 0.023 |

## By tier (non-victim)

### P1

| Policy | Admit | Cond. SLO | Effective goodput | P99 TTFT |
|---|---:|---:|---:|---:|
| `adaptive-slo` | 1.000 | 0.977 | 0.977 | 1811 |
| `slo-aware` | 0.985 | 1.000 | 0.985 | 353 |

### P2

| Policy | Admit | Cond. SLO | Effective goodput | P99 TTFT |
|---|---:|---:|---:|---:|
| `adaptive-slo` | 1.000 | 0.999 | 0.999 | 597 |
| `slo-aware` | 0.914 | 0.974 | 0.890 | 393 |

### P3

| Policy | Admit | Cond. SLO | Effective goodput | P99 TTFT |
|---|---:|---:|---:|---:|
| `adaptive-slo` | 1.000 | 0.996 | 0.996 | 477 |
| `slo-aware` | 0.485 | 0.993 | 0.481 | 339 |

## Selected runs

- `adaptive-slo`: noisy_neighbor-adaptive-slo-r1-20260820-105507; noisy_neighbor-adaptive-slo-r2-20260820-110706; noisy_neighbor-adaptive-slo-r3-20260820-112023; noisy_neighbor-adaptive-slo-r4-20260820-113223; noisy_neighbor-adaptive-slo-r5-20260820-114422
- `slo-aware`: noisy_neighbor-slo-aware-r1-20260819-012547; noisy_neighbor-slo-aware-r2-20260819-013800; noisy_neighbor-slo-aware-r3-20260819-014945; noisy_neighbor-slo-aware-r4-20260819-020142; noisy_neighbor-slo-aware-r5-20260819-021326

## Interpretation checklist

- Does adaptive keep P1/P2 SLO near static?
- Does non-offender P99 stay close to static, or does admit≈1 inflate tails?
- Is goodput gain worth isolation loss?

## Finding (honest)

Adaptive recovers near-100% non-victim goodput (0.997 vs static 0.847) by essentially stopping shedding (throttle 0 vs 0.13). That comes with a clear isolation / tail cost:

- Non-victim P99 rises from ~394 ms (static) to ~624 ms (adaptive).
- P1 P99 is especially hurt (~1811 ms vs ~353 ms) even though P1 admit stays 100%.
- P3 goes from heavily shed under static (admit 0.485) to fully admitted under adaptive — goodput win, weaker noisy-neighbor isolation.

Paper framing: Adaptive is valuable on token-burst elastic capacity; on noisy-neighbor it trades static’s latency protection for higher goodput and weaker tenant isolation. A production controller likely needs a floor on shedding / per-tenant caps so AIMD cannot fully disable isolation.

