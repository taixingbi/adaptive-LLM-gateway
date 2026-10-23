# Adaptive SLO-Aware Admission Control for Multi-Tenant Managed LLM Gateways

Artifact for the IEEE BigData 2026 paper of the same name.

A managed LLM gateway sits in front of an **elastic** provider (here, AWS Bedrock).
A static token budget C is either too small — it sheds healthy traffic — or too
large — it cannot contract when the provider tightens. This repo is a real
multi-tenant gateway plus the evaluation harness that measures an AIMD estimate
Ĉ against that failure mode.

```
Paper claim
───────────
Static SLO-aware at C0 over-sheds a token-size burst.
Adaptive-slo starts at the same C0, grows Ĉ while Bedrock stays healthy,
and recovers most of the goodput that a large static Cmax would admit —
without giving up the ability to shrink on provider 429/5xx.
```

Backend is **real Bedrock Nova Micro CRIS** (`us.amazon.nova-micro-v1:0`).
Overload is enforced by a **synthetic** gateway budget `platform_tpm_budget`,
not by claiming a smaller AWS quota. Account `646821141010` currently has
8M TPM / 400 RPM on that model; C0 = 100k and Cmax = 2M are admission knobs.

## Camera-ready numbers

Do **not** headline the archived warm-state 0.844 / 18×
(`token_burst_comparison.md`). That cell started with Ĉ already at
Cmax. Use the matched 120–300s window below.

**Table IV — token-size burst, t ∈ [120, 300), 5 reps, mean ± sample SD**

| Cell | Effective goodput | Cond. SLO | P99 TTFT | Throttle |
|---|---:|---:|---:|---:|
| NONE | 1.000±0.000 | 1.000±0.000 | 583±84 ms | 0.000 |
| STATIC-SLO @ C0=100k | 0.045±0.003 | 0.942±0.064 | 531±54 ms | 0.952 |
| STATIC-SLO @ Cmax=2M | 0.805±0.054 | 0.980±0.007 | 514±42 ms | 0.179 |
| Adaptive-cold (Ĉ(0)=C0) | **0.519±0.068** | 0.831±0.012 | 516±37 ms | 0.376 |

Source: `analysis/result_paper/token_burst_matched_summary.md`.
Adaptive goodput is ~11.5× static-C0 and still below static-Cmax because the
climb happens *during* the burst. Zero provider 429s in every cell.

**Provider contraction** (`experiments/provider_contraction.yaml`, 5 reps):
Ĉ reaches ~1.95M before external Bedrock pressure, contracts 20% in
~22s and 50% in ~74s, then recovers to 90% in ~144s. See
`analysis/result_paper/contraction_metrics.md`.

**Noisy neighbor** is a different tradeoff, not a second Adaptive win.
Static SLO-aware sheds ~13% and protects tails (P99 ~394 ms). Adaptive
recovers non-victim goodput to ~0.997 but weakens isolation (P1 P99 ~1.8 s).
Write that as a limitation. Details:
`analysis/result_paper/noisy_neighbor_adaptive_comparison.md`.

## Controller

`slo-aware` admits against a **fixed** synthetic C using TTFT slack
(`TTFT_SLO − queue wait − estimated backend TTFT`) and four pressure bands:

| Pressure `load / C` | Action |
|---|---|
| < 0.8 | admit |
| 0.8–1.0 | SLO / priority-aware |
| 1.0–1.1 | reserved share only (`C × weight / 190`) |
| ≥ 1.1 | hard shed |

`adaptive-slo` uses the same bands on Ĉ instead of C. AIMD lives
in `gateway/app/adaptive_capacity.py` and is Redis-backed so both Fargate
tasks share one estimate:

- healthy window → Ĉ ← Ĉ × (1+α)
- Bedrock **429 or 5xx** → Ĉ ← Ĉ × β
- a per-request SLO miss does **not** shrink Ĉ
- defaults: α=0.15, β=0.7, window 15s, C0=100k, Cmax=20×C0=2M
- `POST /v1/admin/reset-adaptive` (SigV4) forces Ĉ(0)=C0 before each Adaptive rep

Baselines: `none`, `rpm`, `tpm`, `token-bucket`, `priority`. Shared counters
are ElastiCache Serverless (`gateway/app/counters.py`).

## Experiments → paper artifacts

| YAML | Paper role | Frozen output |
|---|---|---|
| `experiments/token_burst_coldstart.yaml` | Adaptive cold-start, Ĉ reset to C0, burst 120–300s | `token_burst_coldstart.md`, `adaptive_trace_coldstart_r{1–5}.png` |
| `experiments/token_burst_coldstart_c100k.yaml` | Matched NONE + STATIC-SLO@C0 | `token_burst_matched_summary.md` |
| `experiments/token_burst_coldstart_c2m.yaml` | Matched STATIC-SLO@Cmax | same |
| `experiments/provider_contraction.yaml` | Climb → external pressure → recover | `contraction_metrics.md` |
| `experiments/token_burst.yaml` | 7-policy RPM-blind token burst (180–360s) | `token_burst_burst_phase_summary.md` |
| `experiments/noisy_neighbor.yaml` | Victim `tenant-007` 10×; plot the other 99 | `noisy_neighbor_*.md` |
| `experiments/load_sweep.yaml` | Offered load as % of C (`none`) | `load_sweep_none_summary.md` |
| `experiments/priority.yaml` | Batch vs critical SLO | — |

`token_burst_static_cmax.md` is the **unmatched** archive (180–360s static
mixed with 120–300s Adaptive). Do not put it in Table IV.

Workload shape used for Table IV: 100 tenants, 500 RPM, Nova Micro CRIS,
0–120s short / 120–300s long (5000 in / 256 max tokens) / 300–480s short.
Tenants are 10×P1 / 60×P2 / 30×P3 (`loadgen/tenants.yaml`); the busiest 10
carry ~45% of traffic.

## Reproduce

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r loadgen/requirements.txt -r analysis/requirements.txt
```

The runner deploys policy + budget, optionally resets Ĉ, runs Locust,
syncs S3 JSONL, and writes `analysis/out/<run_id>/summary.json`.
It resets Redis only when `policy == adaptive-slo`.

```bash
# 10-tenant smoke (no Terraform)
.venv/bin/python scripts/run_experiment.py experiments/token_burst_coldstart.yaml \
  --policy adaptive-slo --smoke --skip-deploy

# Camera-ready Adaptive cell (reset Ĉ to 100k every rep)
.venv/bin/python scripts/run_experiment.py experiments/token_burst_coldstart.yaml \
  --policy adaptive-slo --deploy --repetitions 5 --reset-adaptive

# Matched static cells (do not reset Adaptive)
.venv/bin/python scripts/run_experiment.py experiments/token_burst_coldstart_c100k.yaml \
  --all-policies --deploy --no-reset-adaptive
.venv/bin/python scripts/run_experiment.py experiments/token_burst_coldstart_c2m.yaml \
  --policy slo-aware --deploy --no-reset-adaptive

# Contraction / recovery
.venv/bin/python scripts/run_experiment.py experiments/provider_contraction.yaml \
  --policy adaptive-slo --deploy --repetitions 5 --reset-adaptive
```

Rebuild Table IV from the latest r1–r5 of each cell (per-rep `summarize()`,
then `statistics.stdev`, n−1 — requests are not pooled):

```bash
.venv/bin/python analysis/compare_matched_windows.py
.venv/bin/python analysis/plot_contraction.py
```

Paper wording for auth: *For controlled experiments, tenant identities are
injected by the workload generator; the production gateway uses
SigV4-authenticated principals.* Production path is `POST /v1/converse`.
Experiments use `POST /v1/infer` with Locust `tenant_id`.

## System

```
Spoke IAM / Locust                  Gateway (2× Fargate 512/1024)
       │                                    │
       ▼                                    ▼
API Gateway (SigV4) ──► POST /v1/converse or /v1/infer
                              │
                    DynamoDB TenantPolicy
                    Redis Ĉ + TPM/RPM counters
                              │
                    none | rpm | tpm | token-bucket
                    priority | slo-aware | adaptive-slo
                              │
                    Bedrock Nova Micro CRIS
                              │
                    S3 JSONL  →  analysis/result_paper/
```

Dev stack: cluster `bedrock-platform-dev-llm`, service `llm-gateway`,
internal ALB, API `https://w6y8r7auy7.execute-api.us-east-1.amazonaws.com`.
`run_experiment.py --deploy` only changes `ADMISSION_POLICY`,
`PLATFORM_TPM_BUDGET`, AIMD knobs, and `RUN_ID`.

| Knob | Where | Meaning |
|---|---|---|
| `admission_policy` | Terraform / `--policy` | Controller under test |
| `platform_tpm_budget` | YAML or `--platform-tpm-budget` | Synthetic C / C0 |
| `ADAPTIVE_{ALPHA,BETA,WINDOW_S}` | Terraform | AIMD knobs |
| Tenants | `loadgen/tenants.yaml` | 100 logical tenants, one AWS account |

## Deploy (dev)

Terraform state is in S3 `bedrock-platform-tfstate-646821141010`
(`envs/dev/terraform.tfstate`), not in git.

1. Enable Bedrock model access for Nova Micro and Nova Lite.
2. `cd terraform/envs/dev && terraform init && terraform apply` with
   `desired_count = 0`.
3. Push the image, then set `desired_count = 2` and apply again:

```bash
ECR=$(terraform -chdir=terraform/envs/dev output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR"
docker build --platform linux/amd64 -t "$ECR:latest" gateway
docker push "$ECR:latest"
```

4. Seed tenants and smoke both paths:

```bash
python3 scripts/seed_tenants.py --table "$(terraform -chdir=terraform/envs/dev output -raw tenants_table_name)"
./scripts/invoke.sh                    # SigV4 → app-002 → Nova Lite
./scripts/infer.sh tenant-001 short    # experiment tenant_id → Nova Micro
```

First-time IAM/OIDC bootstrap (CI cannot assume a role that does not exist):

```bash
cd terraform/envs/dev
terraform apply -target=module.platform.module.iam
```

QA/prod tfvars stay at `desired_count = 0` until those accounts exist.

## What this repo does not do

EKS, 100 real spoke accounts, Locust-on-ECS, per-app inference profiles,
active-active regions. ElastiCache Serverless has a ~1 GB minimum; setting
`desired_count = 0` stops Fargate but Redis/NAT/ALB still cost money until
destroyed.
