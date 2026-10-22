# Experiment 1 — cold-start climb of Ĉ from C0 (after provider-health fix)

Workload: `experiments/token_burst_coldstart.yaml`, `adaptive-slo`, Ĉ reset to 100k before every rep.
Phases: 0–120s short, 120–300s long burst, 300–480s short. 500 RPM, 100 tenants, 5 reps.

Every rep: **Ĉ(0)=100k → Ĉ_max=2M**. Traces: `adaptive_trace_coldstart_r{1–5}.png`.

Burst window 120–300s mean: admit 0.624, effective goodput **0.519**, cond. SLO 0.831, P99 516 ms, 0 provider 429s.
That is ≫ static-C0 0.046 and below static-Cmax 0.832 (climb is in-window).
