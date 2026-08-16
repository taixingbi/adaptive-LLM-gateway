region                   = "us-east-1"
platform_region          = "us-east-1"
platform_deploy_role_arn = ""
name_prefix              = "spoke-sample"
api_execution_arn        = "arn:aws:execute-api:us-east-1:000000000000:REPLACE"
apps_table_name          = "bedrock-platform-dev-apps"

apps = [
  {
    app_id         = "spoke-app-001"
    team           = "spoke-demo"
    allowed_models = ["claude-sonnet"]
    rpm_limit      = 60
    token_limit    = 20000
  }
]
