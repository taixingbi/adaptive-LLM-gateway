# Central LLM Gateway MVP

One Bedrock control plane per environment. Spoke accounts call the gateway with IAM SigV4. Apps are DynamoDB metadata, not one inference profile per app.

The same gateway is also the paper experiment platform: **real Bedrock backend**, with overload and multi-tenant capacity enforced in the gateway (not by claiming a smaller AWS quota).

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
docker build -t "$ECR:latest" gateway
docker push "$ECR:latest"
```

5. Set `desired_count = 2` in `terraform/envs/dev/terraform.tfvars` and apply again.
6. Seed 100 logical tenants (one AWS account):

```bash
python3 scripts/seed_tenants.py --table "$(terraform -chdir=terraform/envs/dev output -raw tenants_table_name)"
```

7. Assume a sample role and invoke:

```bash
chmod +x scripts/invoke.sh scripts/infer.sh
./scripts/invoke.sh                          # IAM demo: app-002 → Nova Lite
./scripts/infer.sh tenant-001 short          # experiment path: Nova Micro + admission
```

## Experiment architecture

```
Locust  →  API Gateway (IAM)  →  ALB  →  ECS Fargate gateway
                                      →  ElastiCache Serverless (counters)
                                      →  DynamoDB (tenant policy)
                                      →  Bedrock ConverseStream (Nova Micro)
                                      →  S3 JSONL  +  CloudWatch
```

Paper contribution is `gateway/app/admission/slo_aware.py` plus the workload in `experiments/`. AWS, ECS, Redis, DynamoDB, and Bedrock are infrastructure.

| Knob | Where | Notes |
|---|---|---|
| `admission_policy` | `terraform.tfvars` | `none`, `rpm`, `tpm`, `priority`, `slo-aware` |
| `platform_tpm_budget` | `terraform.tfvars` | Synthetic **C**. Sweep load as % of C |
| Tenants | `loadgen/tenants.yaml` | 10×P1 / 60×P2 / 30×P3 |
| Prompts | `loadgen/prompts/` | Known token demand; no CountTokens on the hot path |

Scenarios (do not Cartesian-product every axis):

- `experiments/load_sweep.yaml` — 50/80/100/120/150% of C
- `experiments/noisy_neighbor.yaml` — tenant-007 10× burst; plot the other 99
- `experiments/token_burst.yaml` — constant RPM, token size jump
- `experiments/priority.yaml` — batch vs critical SLO

First run 10 tenants / 20 RPM / 5 minutes and confirm TTFT, Redis counters, and S3 JSONL. Then algorithms. Full 100-tenant matrix last.

```bash
# Offline token stamp (once per prompt set)
python3 scripts/count_tokens.py

# Loadgen (smoke). Use the app-002 invoke role so SigV4 is allowed.
GATEWAY_URL=$(terraform -chdir=terraform/envs/dev output -raw api_endpoint) \
LOADGEN_ROLE_ARN=$(terraform -chdir=terraform/envs/dev output -json sample_role_arns | python3 -c 'import json,sys; print(json.load(sys.stdin)["app-002"])') \
  locust -f loadgen/locustfile.py --users 10 --spawn-rate 2 --run-time 5m --headless

# Plots from gateway events (source of truth)
python3 analysis/plots.py s3://$(terraform -chdir=terraform/envs/dev output -raw results_bucket)/results
```

Download JSONL from the results bucket before plotting if you are not using `s3://` directly (`plots.py` reads a local directory of `.jsonl` files).

## Auth

Callers use `execute-api:Invoke` with SigV4. API Gateway maps `$context.identity.userArn` to `x-caller-arn`. The gateway looks up that principal (STS assumed-role ARNs are normalized to IAM role ARNs) in DynamoDB. `/v1/infer` is the experiment API: tenant identity is `tenant_id` in the body (100 logical apps, not 100 AWS accounts).

## Capacity

Bedrock runtime TPM is model-level and counts input+output tokens. Request a quota increase if the *real* AWS cap sits below the offered load you need. Gateway admission still uses `platform_tpm_budget` so overload is repeatable even when AWS headroom is large.

## What this repo does not do yet

EKS, 100 real spoke accounts, Locust-on-ECS service, per-app inference profiles, active-active gateway regions. ElastiCache Serverless has a ~1 GB minimum; turn `desired_count` to 0 when idle, but Redis/NAT/ALB still cost money until destroyed.
