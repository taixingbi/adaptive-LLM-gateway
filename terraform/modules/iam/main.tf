variable "name_prefix" {
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

variable "tags" {
  type    = map(string)
  default = {}
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_iam_role" "ecs_execution" {
  name = "${var.name_prefix}-ecs-execution"
  tags = var.tags
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "${var.name_prefix}-ecs-task"
  tags = var.tags
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task" {
  name = "gateway"
  role = aws_iam_role.ecs_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockConverse"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Converse",
          "bedrock:ConverseStream",
          "bedrock:CountTokens",
          "bedrock:GetInferenceProfile"
        ]
        Resource = "*"
      },
      {
        Sid    = "MarketplaceModelAccess"
        Effect = "Allow"
        Action = [
          "aws-marketplace:ViewSubscriptions",
          "aws-marketplace:Subscribe"
        ]
        Resource = "*"
      },
      {
        Sid    = "DynamoDB"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.name_prefix}-apps",
          "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.name_prefix}-apps/index/*",
          "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.name_prefix}-rate-limits",
          "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.name_prefix}-tenants"
        ]
      },
      {
        Sid    = "ResultsBucket"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:AbortMultipartUpload"]
        Resource = [
          "arn:aws:s3:::${var.name_prefix}-exp-results",
          "arn:aws:s3:::${var.name_prefix}-exp-results/*"
        ]
      },
      {
        Sid      = "Metrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
        Condition = {
          StringEquals = { "cloudwatch:namespace" = "BedrockPlatform" }
        }
      }
    ]
  })
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.github_org == "" ? 0 : 1
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS ignores GitHub IdP thumbprints; a placeholder is still required by the API.
  thumbprint_list = ["ffffffffffffffffffffffffffffffffffffffff"]
  tags            = var.tags
}

resource "aws_iam_role" "github_actions" {
  count = var.github_org == "" ? 0 : 1
  name  = "github-actions-bedrock-platform"
  tags  = var.tags
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github[0].arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          # Classic sub (repos created before 15 Jul 2026) and immutable sub
          # (repo:org@ORG_ID/name@REPO_ID:...) used by this repo.
          "token.actions.githubusercontent.com:sub" = [
            "repo:${var.github_org}/${var.github_repo}:*",
            "repo:${var.github_org}@*/${var.github_repo}@*:*",
          ]
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_actions" {
  count = var.github_org == "" ? 0 : 1
  name  = "deploy"
  role  = aws_iam_role.github_actions[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ecr:*",
        "ecs:*",
        "iam:*",
        "logs:*",
        "elasticloadbalancing:*",
        "apigateway:*",
        "dynamodb:*",
        "bedrock:*",
        "ec2:*",
        "cloudwatch:*",
        "application-autoscaling:*",
        "s3:*",
        "elasticache:*"
      ]
      Resource = "*"
    }]
  })
}

output "ecs_execution_role_arn" {
  value = aws_iam_role.ecs_execution.arn
}

output "ecs_task_role_arn" {
  value = aws_iam_role.ecs_task.arn
}

output "github_actions_role_arn" {
  value = try(aws_iam_role.github_actions[0].arn, "")
}

output "github_actions_role_name" {
  value = "github-actions-bedrock-platform"
}
