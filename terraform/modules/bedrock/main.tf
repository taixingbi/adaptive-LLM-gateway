variable "name_prefix" {
  type = string
}

variable "account_id" {
  type = string
}

variable "region" {
  type = string
}

variable "models" {
  type = map(object({
    source_model_id = string
  }))
  default = {
    claude-sonnet = { source_model_id = "us.anthropic.claude-3-5-sonnet-20241022-v2:0" }
    claude-haiku  = { source_model_id = "us.anthropic.claude-3-5-haiku-20241022-v1:0" }
    nova-lite     = { source_model_id = "us.amazon.nova-lite-v1:0" }
    llama         = { source_model_id = "us.meta.llama3-3-70b-instruct-v1:0" }
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_bedrock_inference_profile" "shared" {
  for_each    = var.models
  name        = replace("${var.name_prefix}-${each.key}", "_", "-")
  description = "Shared ${each.key} CRIS profile"

  model_source {
    copy_from = "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/${each.value.source_model_id}"
  }

  tags = merge(var.tags, { ModelAlias = each.key })
}

output "profile_arns" {
  value = { for k, v in aws_bedrock_inference_profile.shared : k => v.arn }
}

output "model_map_json" {
  value = jsonencode({ for k, v in aws_bedrock_inference_profile.shared : k => v.arn })
}
