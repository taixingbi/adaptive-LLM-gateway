# Central LLM Gateway MVP

One Bedrock control plane per environment. Spoke accounts call the gateway with IAM SigV4. Apps are DynamoDB metadata, not one inference profile per app.

## Accounts

| Terraform env | Account name | Apply first? |
|---|---|---|
| `terraform/envs/dev` | `bedrock-platform-dev` | yes |
| `terraform/envs/qa` | `bedrock-platform-qa` | after dev |
| `terraform/envs/prod` | `bedrock-platform-prod` | last |

Fill the real 12-digit `account_id` in each `terraform.tfvars`. Those files are config, not secrets. GitHub Actions secrets stay empty: CI assumes `github-actions-bedrock-platform` via OIDC after you set `github_org`.

## Apply order (dev)

1. Enable Bedrock model access in `bedrock-platform-dev` for the CRIS models in [`terraform/modules/bedrock/main.tf`](terraform/modules/bedrock/main.tf) (Claude Sonnet/Haiku, Nova Lite, Llama).
2. `cd terraform/envs/dev && terraform init && terraform apply` with `desired_count = 0`.
3. Push the image:

```bash
ECR=$(terraform -chdir=terraform/envs/dev output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR"
docker build -t "$ECR:latest" gateway
docker push "$ECR:latest"
```

4. Set `desired_count = 2` in `terraform/envs/dev/terraform.tfvars` and apply again.
5. Assume a sample role from `terraform output sample_role_arns` and invoke:

```bash
python scripts/invoke.py --url "$(terraform -chdir=terraform/envs/dev output -raw converse_url)" --region us-east-1
```

## Auth

Callers use `execute-api:Invoke` with SigV4. API Gateway maps `$context.identity.userArn` to `x-caller-arn`. The gateway looks up that principal (STS assumed-role ARNs are normalized to IAM role ARNs) in DynamoDB.

## Capacity

3000 requests/min is about 50 RPS. ECS scales horizontally. Check Bedrock RPM/TPM quotas per model; use the shared cross-Region inference profiles and request quota increases if a single Region is short.

## What this repo does not do yet

EKS, 100 real spokes, 1000 real apps, per-app inference profiles, prompt storage, Redis, active-active gateway regions.
