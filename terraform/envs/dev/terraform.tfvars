account_name = "bedrock-platform-dev"
account_id   = "646821141010"
region       = "us-east-1"

# GitHub org/user that owns this repo (OIDC trust). Empty skips the CI role.
github_org  = "taixingbi"
github_repo = "bedrock-platform"

# Stay at 0 until the gateway image is pushed to ECR, then set to 2.
desired_count = 0

apps = [
  {
    app_id         = "app-001"
    team           = "demo"
    allowed_models = ["claude-sonnet"]
    rpm_limit      = 100
    token_limit    = 50000
  },
  {
    app_id         = "app-002"
    team           = "demo"
    allowed_models = ["nova-lite"]
    rpm_limit      = 300
    token_limit    = 100000
  },
  {
    app_id         = "app-003"
    team           = "demo"
    allowed_models = ["claude-haiku"]
    rpm_limit      = 50
    token_limit    = 25000
  }
]
