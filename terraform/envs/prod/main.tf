terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.90"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

variable "account_name" { type = string }
variable "account_id" { type = string }
variable "region" { type = string }
variable "github_org" {
  type    = string
  default = ""
}
variable "github_repo" {
  type    = string
  default = "bedrock-platform"
}
variable "desired_count" {
  type    = number
  default = 0
}
variable "apps" {
  type = list(object({
    app_id         = string
    team           = string
    allowed_models = list(string)
    rpm_limit      = number
    token_limit    = number
  }))
  default = []
}

module "platform" {
  source        = "../../modules/platform"
  account_name  = var.account_name
  account_id    = var.account_id
  region        = var.region
  github_org    = var.github_org
  github_repo   = var.github_repo
  desired_count = var.desired_count
  cpu           = 1024
  memory        = 2048
}

module "apps" {
  source   = "../../modules/app-onboarding"
  for_each = { for app in var.apps : app.app_id => app }

  providers = {
    aws.spoke    = aws
    aws.platform = aws
  }

  name_prefix       = var.account_name
  app_id            = each.value.app_id
  team              = each.value.team
  allowed_models    = each.value.allowed_models
  rpm_limit         = each.value.rpm_limit
  token_limit       = each.value.token_limit
  api_execution_arn = module.platform.api_execution_arn
  apps_table_name   = module.platform.apps_table_name
}

output "ecr_repository_url" { value = module.platform.ecr_repository_url }
output "api_endpoint" { value = module.platform.api_endpoint }
output "converse_url" { value = module.platform.converse_url }
output "github_actions_role_arn" { value = module.platform.github_actions_role_arn }
output "model_map" { value = module.platform.model_map }
output "sample_role_arns" { value = { for k, v in module.apps : k => v.role_arn } }
