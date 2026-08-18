account_name = "bedrock-platform-dev"
account_id   = "646821141010"
region       = "us-east-1"

# GitHub org/user that owns this repo (OIDC trust). Empty skips the CI role.
github_org  = "taixingbi"
github_repo = "bedrock-platform"

# Image is in ECR; run 2 Fargate tasks behind the ALB.
desired_count = 2

# Paper experiment knobs. PLATFORM_TPM_BUDGET is a synthetic capacity
# budget, not "AWS Bedrock only supports 100k TPM".
# admission_policy: none | rpm | tpm | token-bucket | priority | slo-aware
admission_policy    = "none"
platform_tpm_budget = 100000
run_id              = "dev"

apps = [
  {
    app_id         = "app-002"
    team           = "demo"
    allowed_models = ["nova-lite"]
    rpm_limit      = 300
    token_limit    = 100000
  }
]
