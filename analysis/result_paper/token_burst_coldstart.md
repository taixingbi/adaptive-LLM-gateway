# Experiment 1 — cold-start climb of Ĉ from C0

Workload: `experiments/token_burst_coldstart.yaml`, `adaptive-slo`, Ĉ reset to 100k before every rep.  
Phases: 0–120s short, 120–300s long burst, 300–480s short. 500 RPM, 100 tenants, 5 reps.

Traces: `adaptive_trace_coldstart_r{1–5}.png` (+ `.csv`). These replace the leftover-Cmax Fig. 5.

The companion 360s token-burst adaptive cell (Exp 2) also starts at C0 and is in `token_burst_static_cmax.md`. That burst-window goodput is lower than the archived leftover-Ĉ=2M adaptive number (0.844), which is the point of the cold-start rerun.
