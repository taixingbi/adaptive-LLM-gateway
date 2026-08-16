variable "account_name" {
  type = string
}

variable "account_id" {
  type = string
}

variable "region" {
  type = string
}

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

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "models" {
  type = map(object({
    source_model_id = string
  }))
  default = {
    claude-haiku = { source_model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0" }
    nova-lite    = { source_model_id = "us.amazon.nova-lite-v1:0" }
    llama        = { source_model_id = "us.meta.llama3-3-70b-instruct-v1:0" }
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  name_prefix = var.account_name
  tags = merge(var.tags, {
    Project     = "bedrock-platform"
    AccountName = var.account_name
  })
}

module "networking" {
  source      = "../networking"
  name_prefix = local.name_prefix
  vpc_cidr    = var.vpc_cidr
  tags        = local.tags
}

module "iam" {
  source      = "../iam"
  name_prefix = local.name_prefix
  github_org  = var.github_org
  github_repo = var.github_repo
  tags        = local.tags
}

module "bedrock" {
  source      = "../bedrock"
  name_prefix = local.name_prefix
  account_id  = var.account_id
  region      = var.region
  models      = var.models
  tags        = local.tags
}

module "llm_gateway" {
  source                 = "../llm-gateway"
  name_prefix            = local.name_prefix
  vpc_id                 = module.networking.vpc_id
  private_subnet_ids     = module.networking.private_subnet_ids
  ecs_execution_role_arn = module.iam.ecs_execution_role_arn
  ecs_task_role_arn      = module.iam.ecs_task_role_arn
  model_map_json         = module.bedrock.model_map_json
  desired_count          = var.desired_count
  cpu                    = var.cpu
  memory                 = var.memory
  tags                   = local.tags
}

module "monitoring" {
  source         = "../monitoring"
  name_prefix    = local.name_prefix
  cluster_name   = module.llm_gateway.cluster_name
  service_name   = module.llm_gateway.service_name
  alb_arn_suffix = module.llm_gateway.alb_arn_suffix
  log_group_name = module.llm_gateway.log_group_name
  tags           = local.tags
}

output "ecr_repository_url" {
  value = module.llm_gateway.ecr_repository_url
}

output "api_endpoint" {
  value = module.llm_gateway.api_endpoint
}

output "api_execution_arn" {
  value = module.llm_gateway.api_execution_arn
}

output "apps_table_name" {
  value = module.llm_gateway.apps_table_name
}

output "github_actions_role_arn" {
  value = module.iam.github_actions_role_arn
}

output "model_map" {
  value = module.bedrock.profile_arns
}

output "converse_url" {
  value = "${module.llm_gateway.api_endpoint}/v1/converse"
}
