terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      configuration_aliases = [aws.spoke, aws.platform]
    }
  }
}

variable "name_prefix" {
  type = string
}

variable "app_id" {
  type = string
}

variable "team" {
  type = string
}

variable "allowed_models" {
  type = list(string)
}

variable "rpm_limit" {
  type = number
}

variable "token_limit" {
  type = number
}

variable "api_execution_arn" {
  type = string
}

variable "apps_table_name" {
  type = string
}

variable "trusted_principal_arns" {
  type        = list(string)
  description = "Principals in the spoke account allowed to assume the invoke role. Empty = spoke account root."
  default     = []
}

variable "tags" {
  type    = map(string)
  default = {}
}

data "aws_caller_identity" "spoke" {
  provider = aws.spoke
}

locals {
  trusted = length(var.trusted_principal_arns) > 0 ? var.trusted_principal_arns : ["arn:aws:iam::${data.aws_caller_identity.spoke.account_id}:root"]
}

resource "aws_iam_role" "invoke" {
  provider = aws.spoke
  name     = "${var.name_prefix}-app-${var.app_id}"
  tags     = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = local.trusted }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "invoke" {
  provider = aws.spoke
  name     = "execute-api"
  role     = aws_iam_role.invoke.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "execute-api:Invoke"
      Resource = "${var.api_execution_arn}/*"
    }]
  })
}

resource "aws_dynamodb_table_item" "app" {
  provider   = aws.platform
  table_name = var.apps_table_name
  hash_key   = "app_id"

  item = jsonencode({
    app_id         = { S = var.app_id }
    principal_arn  = { S = aws_iam_role.invoke.arn }
    account_id     = { S = data.aws_caller_identity.spoke.account_id }
    team           = { S = var.team }
    allowed_models = { SS = var.allowed_models }
    rpm_limit      = { N = tostring(var.rpm_limit) }
    token_limit    = { N = tostring(var.token_limit) }
  })
}

output "role_arn" {
  value = aws_iam_role.invoke.arn
}
