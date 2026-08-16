variable "name_prefix" {
  type = string
}

variable "account_id" {
  type = string
}

variable "region" {
  type = string
}

variable "create_application_profiles" {
  type        = bool
  default     = false
  description = "Create Bedrock application inference profiles. Off by default: many accounts cannot call CreateInferenceProfile. System CRIS model IDs are shared across apps either way."
}

variable "models" {
  type = map(object({
    source_model_id = string
  }))
  default = {
    claude-sonnet = { source_model_id = "us.anthropic.claude-sonnet-4-20250514-v1:0" }
    claude-haiku  = { source_model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0" }
    nova-lite     = { source_model_id = "us.amazon.nova-lite-v1:0" }
    llama         = { source_model_id = "us.meta.llama3-3-70b-instruct-v1:0" }
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_bedrock_inference_profile" "shared" {
  for_each    = var.create_application_profiles ? var.models : {}
  name        = replace("${var.name_prefix}-${each.key}", "_", "-")
  description = "Shared ${each.key} CRIS profile"

  model_source {
    copy_from = "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/${each.value.source_model_id}"
  }

  tags = merge(var.tags, { ModelAlias = each.key })
}

output "profile_arns" {
  value = var.create_application_profiles ? { for k, v in aws_bedrock_inference_profile.shared : k => v.arn } : { for k, v in var.models : k => v.source_model_id }
}

output "model_map_json" {
  value = jsonencode(var.create_application_profiles ? { for k, v in aws_bedrock_inference_profile.shared : k => v.arn } : { for k, v in var.models : k => v.source_model_id })
}
