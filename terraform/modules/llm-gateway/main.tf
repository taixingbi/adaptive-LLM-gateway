variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "ecs_execution_role_arn" {
  type = string
}

variable "ecs_task_role_arn" {
  type = string
}

variable "model_map_json" {
  type = string
}

variable "container_image" {
  type        = string
  default     = ""
  description = "Leave empty to use this module's ECR repo :latest tag."
}

variable "desired_count" {
  type    = number
  default = 2
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "admission_policy" {
  type    = string
  default = "none"
}

variable "platform_tpm_budget" {
  type    = number
  default = 100000
}

variable "experiment_model_id" {
  type    = string
  default = "us.amazon.nova-micro-v1:0"
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

variable "tags" {
  type    = map(string)
  default = {}
}

data "aws_region" "current" {}

locals {
  image = var.container_image != "" ? var.container_image : "${aws_ecr_repository.gateway.repository_url}:latest"
}

resource "aws_ecr_repository" "gateway" {
  name                 = "${var.name_prefix}-llm-gateway"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  tags                 = var.tags

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/ecs/${var.name_prefix}-llm-gateway"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_dynamodb_table" "apps" {
  name         = "${var.name_prefix}-apps"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "app_id"
  tags         = var.tags

  attribute {
    name = "app_id"
    type = "S"
  }

  attribute {
    name = "principal_arn"
    type = "S"
  }

  global_secondary_index {
    name            = "principal_arn-index"
    hash_key        = "principal_arn"
    projection_type = "ALL"
  }
}

resource "aws_dynamodb_table" "rate_limits" {
  name         = "${var.name_prefix}-rate-limits"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "app_id"
  range_key    = "window"
  tags         = var.tags

  attribute {
    name = "app_id"
    type = "S"
  }

  attribute {
    name = "window"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_dynamodb_table" "tenants" {
  name         = "${var.name_prefix}-tenants"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "tenant_id"
  tags         = var.tags

  attribute {
    name = "tenant_id"
    type = "S"
  }
}

resource "aws_s3_bucket" "results" {
  bucket        = "${var.name_prefix}-exp-results"
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_public_access_block" "results" {
  bucket                  = aws_s3_bucket.results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis"
  description = "ElastiCache Serverless for quota counters"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-redis" })
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_ecs" {
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = aws_security_group.ecs.id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}

resource "aws_vpc_security_group_egress_rule" "redis_all" {
  security_group_id = aws_security_group.redis.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_elasticache_serverless_cache" "quota" {
  engine               = "redis"
  name                 = replace(substr("${var.name_prefix}-quota", 0, 40), "_", "-")
  major_engine_version = "7"
  description          = "Shared TPM/RPM/concurrency counters for admission control"
  security_group_ids   = [aws_security_group.redis.id]
  subnet_ids           = var.private_subnet_ids
  tags                 = var.tags

  cache_usage_limits {
    data_storage {
      maximum = 1
      unit    = "GB"
    }
    ecpu_per_second {
      maximum = 1000
    }
  }

  timeouts {
    create = "45m"
    delete = "45m"
  }
}

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "Internal ALB"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-alb" })
}

resource "aws_security_group" "vpc_link" {
  name        = "${var.name_prefix}-vpclink"
  description = "API Gateway VPC Link"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-vpclink" })
}

resource "aws_security_group" "ecs" {
  name        = "${var.name_prefix}-ecs"
  description = "Gateway tasks"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-ecs" })
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_vpclink" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.vpc_link.id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_vpc_security_group_egress_rule" "alb_all" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_egress_rule" "vpclink_to_alb" {
  security_group_id            = aws_security_group.vpc_link.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
}

resource "aws_vpc_security_group_ingress_rule" "ecs_from_alb" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
}

resource "aws_vpc_security_group_egress_rule" "ecs_all" {
  security_group_id = aws_security_group.ecs.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_lb" "this" {
  name               = substr("${var.name_prefix}-gw", 0, 32)
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.private_subnet_ids
  tags               = var.tags
}

resource "aws_lb_target_group" "this" {
  name        = substr("${var.name_prefix}-gw", 0, 32)
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"
  tags        = var.tags

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 15
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "this" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }
}

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-llm"
  tags = var.tags

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "this" {
  family                   = "${var.name_prefix}-llm-gateway"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn            = var.ecs_task_role_arn
  tags                     = var.tags

  container_definitions = jsonencode([{
    name      = "gateway"
    image     = local.image
    essential = true
    portMappings = [{
      containerPort = 8080
      protocol      = "tcp"
    }]
    environment = [
      { name = "AWS_REGION", value = data.aws_region.current.name },
      { name = "APPS_TABLE", value = aws_dynamodb_table.apps.name },
      { name = "RATE_LIMITS_TABLE", value = aws_dynamodb_table.rate_limits.name },
      { name = "TENANTS_TABLE", value = aws_dynamodb_table.tenants.name },
      { name = "CALLER_ARN_HEADER", value = "x-caller-arn" },
      { name = "MODEL_MAP_JSON", value = var.model_map_json },
      { name = "METRICS_NAMESPACE", value = "BedrockPlatform" },
      { name = "ADMISSION_POLICY", value = var.admission_policy },
      { name = "PLATFORM_TPM_BUDGET", value = tostring(var.platform_tpm_budget) },
      { name = "EXPERIMENT_MODEL_ID", value = var.experiment_model_id },
      { name = "REDIS_URL", value = "rediss://${aws_elasticache_serverless_cache.quota.endpoint[0].address}:${aws_elasticache_serverless_cache.quota.endpoint[0].port}" },
      { name = "RESULTS_BUCKET", value = aws_s3_bucket.results.bucket },
      { name = "RUN_ID", value = var.run_id },
      { name = "ADAPTIVE_ALPHA", value = tostring(var.adaptive_alpha) },
      { name = "ADAPTIVE_BETA", value = tostring(var.adaptive_beta) },
      { name = "ADAPTIVE_WINDOW_S", value = tostring(var.adaptive_window_s) }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.gateway.name
        awslogs-region        = data.aws_region.current.name
        awslogs-stream-prefix = "gateway"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')\""]
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 20
    }
  }])
}

resource "aws_ecs_service" "this" {
  name            = "llm-gateway"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.this.arn
    container_name   = "gateway"
    container_port   = 8080
  }

  depends_on = [aws_lb_listener.this]
}

resource "aws_apigatewayv2_vpc_link" "this" {
  name               = "${var.name_prefix}-gw"
  security_group_ids = [aws_security_group.vpc_link.id]
  subnet_ids         = var.private_subnet_ids
  tags               = var.tags
}

resource "aws_apigatewayv2_api" "this" {
  name          = "${var.name_prefix}-llm-gateway"
  protocol_type = "HTTP"
  tags          = var.tags
}

resource "aws_apigatewayv2_integration" "this" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = aws_lb_listener.this.arn
  connection_type        = "VPC_LINK"
  connection_id          = aws_apigatewayv2_vpc_link.this.id
  payload_format_version = "1.0"

  request_parameters = {
    "overwrite:header.x-caller-arn" = "$context.identity.userArn"
    "overwrite:header.x-caller"     = "$context.identity.caller"
  }
}

resource "aws_apigatewayv2_route" "converse" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "POST /v1/converse"
  authorization_type = "AWS_IAM"
  target             = "integrations/${aws_apigatewayv2_integration.this.id}"
}

resource "aws_apigatewayv2_route" "infer" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "POST /v1/infer"
  authorization_type = "AWS_IAM"
  target             = "integrations/${aws_apigatewayv2_integration.this.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true
  tags        = var.tags
  depends_on  = [aws_cloudwatch_log_resource_policy.apigw]

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.apigw.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      caller         = "$context.identity.caller"
      userArn        = "$context.identity.userArn"
      status         = "$context.status"
      integration    = "$context.integrationErrorMessage"
      responseLength = "$context.responseLength"
    })
  }
}

resource "aws_cloudwatch_log_group" "apigw" {
  name              = "/apigateway/${var.name_prefix}-llm-gateway"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_cloudwatch_log_resource_policy" "apigw" {
  policy_name = "${var.name_prefix}-apigw-access"
  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "apigateway.amazonaws.com" }
      Action    = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource  = "${aws_cloudwatch_log_group.apigw.arn}:*"
    }]
  })
}

output "ecr_repository_url" {
  value = aws_ecr_repository.gateway.repository_url
}

output "api_endpoint" {
  value = aws_apigatewayv2_api.this.api_endpoint
}

output "api_execution_arn" {
  value = aws_apigatewayv2_api.this.execution_arn
}

output "apps_table_name" {
  value = aws_dynamodb_table.apps.name
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "service_name" {
  value = aws_ecs_service.this.name
}

output "alb_arn_suffix" {
  value = aws_lb.this.arn_suffix
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.gateway.name
}

output "results_bucket" {
  value = aws_s3_bucket.results.bucket
}

output "tenants_table_name" {
  value = aws_dynamodb_table.tenants.name
}

output "alb_dns_name" {
  value = aws_lb.this.dns_name
}
