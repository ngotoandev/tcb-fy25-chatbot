resource "aws_ecs_cluster" "main" {
  name = local.name
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 7
}

resource "aws_security_group" "svc" {
  name_prefix = "${local.name}-svc-"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port       = local.app_port
    to_port         = local.app_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name         = "app"
    image        = local.image
    essential    = true
    portMappings = [{ containerPort = local.app_port, protocol = "tcp" }]
    environment = [
      { name = "BEDROCK_REGION", value = var.region },
      { name = "LLM_PROVIDER", value = var.llm_provider },
      { name = "SESSION_STORE", value = "dynamo" },
      { name = "SESSIONS_TABLE", value = aws_dynamodb_table.sessions.name },
      { name = "MOCK_LLM", value = "false" },
    ]
    # Vendor API key injected from Secrets Manager (direct-API providers only).
    # for-expression over the count-0/1 secret keeps this valid when it doesn't exist.
    secrets = [for s in aws_secretsmanager_secret.llm_api_key : {
      name      = lookup(local.api_key_env, var.llm_provider, "ANTHROPIC_API_KEY")
      valueFrom = s.arn
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "app"
      }
    }
  }])
}

resource "aws_ecs_service" "app" {
  name            = local.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.svc.id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = local.app_port
  }
  # Give a cold first task time to pull the multi-stage image + attach its ENI
  # before ALB health signals can trigger a replace loop.
  health_check_grace_period_seconds = 120
  # Ensure the task/execution IAM policies exist before the first task launches,
  # so the initial task isn't denied Bedrock/DynamoDB/ECR on a first apply.
  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy.task,
    aws_iam_role_policy_attachment.execution,
    aws_iam_role_policy.execution_secrets,         # secret-read grant (if any)
    aws_secretsmanager_secret_version.llm_api_key, # key value populated before launch
  ]
}
