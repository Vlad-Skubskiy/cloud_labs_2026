resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/notes-worker"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "notes-worker-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.worker_task.arn

  container_definitions = jsonencode([
    {
      name        = "notes-worker"
      image       = local.app_image
      essential   = true
      command     = ["python", "worker.py"]
      stopTimeout = 45
      environment = [
        { name = "REDIS_URL", value = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0" },
        { name = "SQS_QUEUE_URL", value = aws_sqs_queue.jobs.url },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "MAX_RECEIVE_COUNT", value = tostring(var.queue_max_receive_count) },
        { name = "WORKER_CONCURRENCY", value = tostring(var.worker_concurrency) },
        { name = "WORKER_SIMULATED_WORK_MS", value = tostring(var.worker_simulated_work_ms) },
      ]
      secrets = [{
        name      = "DATABASE_URL"
        valueFrom = aws_secretsmanager_secret.database_url.arn
      }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "worker" {
  name            = "notes-worker-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_min_capacity
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_sg.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [
    aws_iam_role_policy_attachment.ecs_execution_role_policy,
    aws_iam_role_policy.read_db_secret,
    aws_secretsmanager_secret_version.database_url,
    null_resource.build_and_push,
    aws_nat_gateway.nat,
  ]
}

resource "aws_appautoscaling_target" "worker" {
  min_capacity       = var.worker_min_capacity
  max_capacity       = var.worker_max_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "worker_scale_out" {
  name               = "worker-step-scale-out"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  service_namespace  = aws_appautoscaling_target.worker.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    metric_aggregation_type = "Maximum"
    cooldown                = 60

    step_adjustment {
      metric_interval_lower_bound = 0
      metric_interval_upper_bound = 200
      scaling_adjustment          = 1
    }
    step_adjustment {
      metric_interval_lower_bound = 200
      scaling_adjustment          = 2
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "queue_backlog_high" {
  alarm_name          = "${var.project_name}-queue-backlog-high"
  alarm_description   = "Довжина черги >= ${var.worker_scale_out_backlog} -> додати воркерів"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.jobs.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = var.worker_scale_out_backlog
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.worker_scale_out.arn]
}

resource "aws_appautoscaling_policy" "worker_scale_in" {
  name               = "worker-step-scale-in"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  service_namespace  = aws_appautoscaling_target.worker.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    metric_aggregation_type = "Maximum"
    cooldown                = 120

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = -1
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "queue_backlog_low" {
  alarm_name          = "${var.project_name}-queue-backlog-low"
  alarm_description   = "Черга майже порожня 5 хвилин -> прибрати воркера"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.jobs.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 5
  threshold           = 10
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_appautoscaling_policy.worker_scale_in.arn]
}

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.project_name}-dlq-not-empty"
  alarm_description   = "У dead-letter queue є повідомлення"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.jobs_dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
