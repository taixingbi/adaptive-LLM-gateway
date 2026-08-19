# Central LLM Gateway MVP

One Bedrock control plane per environment. Spoke accounts call the gateway with IAM SigV4. Apps are DynamoDB metadata, not one inference profile per app.

The same repo is the paper evaluation harness: **real Bedrock backend**, with overload and multi-tenant capacity enforced in the gateway (not by claiming a smaller AWS quota).

```
Production platform                         Research evaluation
────────────────────                        ───────────────────
Spoke AWS accounts                          Locust virtual users
       ↓                                           ↓
IAM SigV4                                   POST /v1/infer
       ↓                                    (tenant_id from loadgen)
API Gateway                                        ↓
       ↓                                    100 logical tenants
POST /v1/converse                           DynamoDB TenantPolicy
       ↓                                           ↓
DynamoDB principal → app                    none | rpm | tpm | token-bucket
       ↓                                    priority | slo-aware
Bedrock CRIS                                       ↓
                                            Redis counters
                                            Bedrock Nova Micro
                                            S3 JSONL
```

## Accounts

| Terraform env | Account name | Apply first? |
|---|---|---|
| `terraform/envs/dev` | `bedrock-platform-dev` | yes |
| `terraform/envs/qa` | `bedrock-platform-qa` | after dev |
| `terraform/envs/prod` | `bedrock-platform-prod` | last |

`terraform/envs/dev/terraform.tfvars` uses account `646821141010` (current AWS CLI identity). Point qa/prod at their own 12-digit IDs when those accounts exist. GitHub Actions secrets stay empty.

This repo was created after 15 Jul 2026, so GitHub OIDC `sub` is `repo:taixingbi@ORG_ID/bedrock-platform@REPO_ID:...`. The IAM trust policy matches both that format and the older `repo:org/repo:*` form.

Terraform state is in S3 bucket `bedrock-platform-tfstate-646821141010` (keys `envs/{dev,qa,prod}/terraform.tfstate`), not in git. CI and laptops must share that backend so IAM/OIDC created locally is not recreated.

**Bootstrap once from your laptop** (CI cannot assume a role that does not exist yet):

```bash
cd terraform/envs/dev
# set account_id to the bedrock-platform-dev 12-digit id
terraform apply -target=module.platform.module.iam
```

Then the `dev` workflow can assume `github-actions-bedrock-platform`.

## Apply order (dev)

1. Enable Bedrock model access in `bedrock-platform-dev` for **Nova Micro** (`us.amazon.nova-micro-v1:0`) and Nova Lite (demo `invoke.sh` still uses Lite).
2. After apply, check the *applied* Bedrock runtime TPM quota for Nova Micro. Experiments use a separate synthetic budget `platform_tpm_budget` (default 100,000 TPM). That budget is **not** "AWS only supports 100k TPM".
3. `cd terraform/envs/dev && terraform init && terraform apply` with `desired_count = 0`.
4. Push the image:

```bash
ECR=$(terraform -chdir=terraform/envs/dev output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR"
docker build --platform linux/amd64 -t "$ECR:latest" gateway
docker push "$ECR:latest"
```

5. Set `desired_count = 2` in `terraform/envs/dev/terraform.tfvars` and apply again.
6. Seed 100 logical tenants (one AWS account, `tenant-001` … `tenant-100`):

```bash
python3 scripts/seed_tenants.py --table "$(terraform -chdir=terraform/envs/dev output -raw tenants_table_name)"
```

7. Assume a sample role and invoke:

```bash
chmod +x scripts/invoke.sh scripts/infer.sh
./scripts/invoke.sh                          # production path: SigV4 → app-002 → Nova Lite
./scripts/infer.sh tenant-001 short          # experiment path: loadgen tenant_id → Nova Micro
```

## Auth

**Production** (`POST /v1/converse`): callers use `execute-api:Invoke` with SigV4. API Gateway maps `$context.identity.userArn` to `x-caller-arn`. The gateway looks up that principal (STS assumed-role ARNs are normalized to IAM role ARNs) in DynamoDB.

**Experiments** (`POST /v1/infer`): Locust injects `tenant_id` in the body so 100 logical enterprise tenants can share one gateway. This is **not** a production auth mechanism. Paper wording: *For controlled experiments, tenant identities are injected by the workload generator; the production gateway uses SigV4-authenticated principals.*

## Admission policies

| `admission_policy` | Role |
|---|---|
| `none` | No control |
| `rpm` / `rpm-fixed` | Calendar-minute request limiter |
| `tpm` / `tpm-fixed` | Calendar-minute token window (resets at `HH:MM`) |
| `token-bucket` | Stronger TPM baseline: continuous refill, no minute-boundary reset |
| `priority` | Weighted / tier-aware under pressure |
| `slo-aware` | Paper controller |

`slo-aware` slack is `TTFT_SLO − wait − estimated backend TTFT`. Capacity bands:

- pressure < 0.8: admit
- 0.8–1.0: SLO / priority-aware
- 1.0–1.1: only reserved share (`C × weight / 190`)
- ≥ 1.1: hard shed

Shared quota state lives in **ElastiCache Serverless** (`gateway/app/counters.py`) so gateway replicas see the same TPM/RPM/concurrency/token-bucket values.

| Knob | Where | Notes |
|---|---|---|
| `admission_policy` | `terraform.tfvars` | See table above |
| `platform_tpm_budget` | `terraform.tfvars` | Synthetic **C**. Sweep load as % of C |
| Tenants | `loadgen/tenants.yaml` | 10×P1 / 60×P2 / 30×P3 |
| Prompts | `loadgen/prompts/` | Known token demand; no CountTokens on the hot path |

Scenarios (do not Cartesian-product every axis):

- `experiments/load_sweep.yaml` — 50/80/100/120/150% of C
- `experiments/noisy_neighbor.yaml` — tenant-007 10× burst; plot the other 99
- `experiments/token_burst.yaml` — constant RPM, token size jump (RPM limiter is blind; TPM/SLO are not)
- `experiments/priority.yaml` — batch vs critical SLO

First run 10 tenants smoke, then a noisy-neighbor pilot. YAML files are executed by the runner, not just documentation:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r loadgen/requirements.txt -r analysis/requirements.txt

# 10-tenant smoke against whatever policy the gateway already runs
.venv/bin/python scripts/run_experiment.py experiments/noisy_neighbor.yaml --policy none --smoke --skip-deploy

# Switch ECS policy + run_id, then Locust (slow: terraform apply)
.venv/bin/python scripts/run_experiment.py experiments/noisy_neighbor.yaml --policy slo-aware --smoke --deploy

# Paper matrix (6 policies × 5 reps). Victim tenant-007 bursts 10x; summary excludes them.
.venv/bin/python scripts/run_experiment.py experiments/noisy_neighbor.yaml --all-policies --deploy
```

Locust users are 1:1 with tenants. Each tenant has its own RPM and prompt class (`loadgen/traffic.py`): P1 5–15 RPM short/medium, P2 5–20 mixed, P3 1–10 medium/long, then skew so the busiest 10 tenants carry ~45% of traffic.


```bash
# Offline token stamp (once per prompt set)
python3 scripts/count_tokens.py

# Loadgen (smoke). Use the app-002 invoke role so SigV4 is allowed.
GATEWAY_URL=$(terraform -chdir=terraform/envs/dev output -raw api_endpoint) \
LOADGEN_ROLE_ARN=$(terraform -chdir=terraform/envs/dev output -json sample_role_arns | python3 -c 'import json,sys; print(json.load(sys.stdin)["app-002"])') \
  locust -f loadgen/locustfile.py --users 10 --spawn-rate 2 --run-time 5m --headless

# Plots from gateway events (source of truth)
python3 analysis/plots.py /path/to/downloaded/jsonl

# Simple policy-level view from analysis/archive/*/summary.json
python3 analysis/visualize.py --scenario noisy_neighbor --title "Noisy neighbor policy comparison"
```

Download JSONL from the results bucket before plotting (`plots.py` reads a local directory of `.jsonl` files).

## Capacity

Bedrock runtime TPM is model-level and counts input+output tokens. Request a quota increase if the *real* AWS cap sits below the offered load you need. Gateway admission still uses `platform_tpm_budget` so overload is repeatable even when AWS headroom is large.

## What this repo does not do yet

EKS, 100 real spoke accounts, Locust-on-ECS service, per-app inference profiles, active-active gateway regions. ElastiCache Serverless has a ~1 GB minimum; turn `desired_count` to 0 when idle, but Redis/NAT/ALB still cost money until destroyed.
