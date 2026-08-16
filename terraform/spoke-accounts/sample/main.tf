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
  alias  = "spoke"
}

provider "aws" {
  region = var.platform_region
  alias  = "platform"

  dynamic "assume_role" {
    for_each = var.platform_deploy_role_arn == "" ? [] : [var.platform_deploy_role_arn]
    content {
      role_arn = assume_role.value
    }
  }
}

variable "region" { type = string }
variable "platform_region" { type = string }
variable "platform_deploy_role_arn" {
  type    = string
  default = ""
}
variable "name_prefix" { type = string }
variable "api_execution_arn" { type = string }
variable "apps_table_name" { type = string }
variable "apps" {
  type = list(object({
    app_id         = string
    team           = string
    allowed_models = list(string)
    rpm_limit      = number
    token_limit    = number
  }))
}

module "apps" {
  source   = "../../modules/app-onboarding"
  for_each = { for app in var.apps : app.app_id => app }

  providers = {
    aws.spoke    = aws.spoke
    aws.platform = aws.platform
  }

  name_prefix       = var.name_prefix
  app_id            = each.value.app_id
  team              = each.value.team
  allowed_models    = each.value.allowed_models
  rpm_limit         = each.value.rpm_limit
  token_limit       = each.value.token_limit
  api_execution_arn = var.api_execution_arn
  apps_table_name   = var.apps_table_name
}

output "role_arns" {
  value = { for k, v in module.apps : k => v.role_arn }
}
