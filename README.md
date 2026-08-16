# Central LLM Gateway MVP

One Bedrock control plane per environment. Spoke accounts call the gateway with IAM SigV4. Apps are DynamoDB metadata, not one inference profile per app.

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

1. Enable Bedrock model access in `bedrock-platform-dev` for the CRIS models in [`terraform/modules/bedrock/main.tf`](terraform/modules/bedrock/main.tf) (Claude Haiku, Nova Lite, Llama).
2. `cd terraform/envs/dev && terraform init && terraform apply` with `desired_count = 0`.
3. Push the image:

```bash
ECR=$(terraform -chdir=terraform/envs/dev output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR"
docker build -t "$ECR:latest" gateway
docker push "$ECR:latest"
```

4. Set `desired_count = 2` in `terraform/envs/dev/terraform.tfvars` and apply again.
5. Assume a sample role and invoke (bash, SigV4 via curl):

```bash
chmod +x scripts/invoke.sh
./scripts/invoke.sh                        # app-002 / nova-lite
./scripts/invoke.sh app-002 nova-lite
./scripts/invoke.sh app-003 claude-haiku "Say hello in one word."
```

Or Python: `python3 scripts/invoke.py --url "$(terraform -chdir=terraform/envs/dev output -raw converse_url)" --region us-east-1`

## Auth

Callers use `execute-api:Invoke` with SigV4. API Gateway maps `$context.identity.userArn` to `x-caller-arn`. The gateway looks up that principal (STS assumed-role ARNs are normalized to IAM role ARNs) in DynamoDB.

## Capacity

3000 requests/min is about 50 RPS. ECS scales horizontally. Check Bedrock RPM/TPM quotas per model; use the shared cross-Region inference profiles and request quota increases if a single Region is short.

## What this repo does not do yet

EKS, 100 real spokes, 1000 real apps, per-app inference profiles, prompt storage, Redis, active-active gateway regions.
