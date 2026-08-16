account_name = "bedrock-platform-dev"
account_id   = "646821141010"
region       = "us-east-1"

# GitHub org/user that owns this repo (OIDC trust). Empty skips the CI role.
github_org  = "taixingbi"
github_repo = "bedrock-platform"

# Image is in ECR; run 2 Fargate tasks behind the ALB.
desired_count = 2

apps = [
  {
    app_id         = "app-002"
    team           = "demo"
    allowed_models = ["nova-lite"]
    rpm_limit      = 300
    token_limit    = 100000
  }
]
