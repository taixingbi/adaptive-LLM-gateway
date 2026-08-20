terraform {
  required_version = ">= 1.5.0"
  backend "s3" {
    bucket         = "bedrock-platform-tfstate-646821141010"
    key            = "envs/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "bedrock-platform-tf-lock"
    encrypt        = true
  }
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
      Environment = "dev"
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
variable "admission_policy" {
  type    = string
  default = "none"
}
variable "platform_tpm_budget" {
  type    = number
  default = 100000
}
variable "run_id" {
  type    = string
  default = "dev"
}
variable "adaptive_alpha" {
  type    = number
  default = 0.15
}
variable "adaptive_beta" {
  type    = number
  default = 0.7
}
variable "adaptive_window_s" {
  type    = number
  default = 15
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
  source              = "../../modules/platform"
  account_name        = var.account_name
  account_id          = var.account_id
  region              = var.region
  github_org          = var.github_org
  github_repo         = var.github_repo
  desired_count       = var.desired_count
  admission_policy    = var.admission_policy
  platform_tpm_budget = var.platform_tpm_budget
  run_id              = var.run_id
  adaptive_alpha      = var.adaptive_alpha
  adaptive_beta       = var.adaptive_beta
  adaptive_window_s   = var.adaptive_window_s
  cpu                 = 512
  memory              = 1024
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
output "infer_url" { value = module.platform.infer_url }
output "results_bucket" { value = module.platform.results_bucket }
output "tenants_table_name" { value = module.platform.tenants_table_name }
output "alb_dns_name" { value = module.platform.alb_dns_name }
