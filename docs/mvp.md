# MVP notes

## Layout

- `gateway/` — FastAPI process run on every ECS task (not one task per model).
- `terraform/modules/` — networking, iam, bedrock (shared profiles), llm-gateway, monitoring, app-onboarding, platform.
- `terraform/envs/{dev,qa,prod}` — `bedrock-platform-dev` / `qa` / `prod`.
- `terraform/spoke-accounts/sample` — extra AWS account pattern: IAM role in spoke, DynamoDB item in platform.

## Shared inference profiles

Application inference profiles are capped (1,000 per account/Region) and bind to a model. MVP does **not** call `CreateInferenceProfile` (this account returns 403). The gateway routes aliases to **system** US CRIS IDs (Nova Lite, Llama 3.3). Cost and RBAC stay on `app_id` in CloudWatch and DynamoDB. Set `create_application_profiles = true` later if the account is allowed to copy those system profiles.

Claude models on this account need AWS Marketplace agreements that are not available here; demos use Nova Lite.

## GitHub

No repository secrets. Set `github_org` in tfvars to create `github-actions-bedrock-platform`. The workflow computes `arn:aws:iam::<account_id>:role/github-actions-bedrock-platform` from tfvars.

Local apply: `AWS_PROFILE` / SSO. Never commit access keys.

## Quotas

Gateway at 50 RPS is easy. Bedrock `InvokeModel` RPM/TPM is the constraint. Cross-Region inference on the shared profiles spreads load across `us-east-1` / `us-east-2` / `us-west-2` for US CRIS model IDs (`us.*`).
