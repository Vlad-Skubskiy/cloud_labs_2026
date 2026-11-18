resource "aws_cloudwatch_dashboard" "queue" {
  dashboard_name = "${var.project_name}-queue-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.main.arn_suffix, { stat = "p95", label = "p95" }],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.main.arn_suffix, { stat = "p50", label = "p50" }]
          ]
          view  = "timeSeries", period = 60, region = var.aws_region
          title = "API latency (s) - не росте під навантаженням"
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          metrics = [["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.main.arn_suffix]]
          view    = "timeSeries", stat = "Sum", period = 60, region = var.aws_region
          title   = "API requests per minute"
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6
        properties = {
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.jobs.name, { label = "waiting (visible)" }],
            ["AWS/SQS", "ApproximateNumberOfMessagesNotVisible", "QueueName", aws_sqs_queue.jobs.name, { label = "in flight" }]
          ]
          view  = "timeSeries", stat = "Maximum", period = 60, region = var.aws_region
          title = "Довжина черги"
          annotations = {
            horizontal = [{ label = "Worker scale-out", value = var.worker_scale_out_backlog }]
          }
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6
        properties = {
          metrics = [
            ["ECS/ContainerInsights", "DesiredTaskCount", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.worker.name, { label = "worker desired" }],
            ["ECS/ContainerInsights", "RunningTaskCount", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.worker.name, { label = "worker running" }]
          ]
          view  = "timeSeries", stat = "Average", period = 60, region = var.aws_region
          title = "Worker tasks (масштабується від черги)"
        }
      },
      {
        type = "metric", x = 0, y = 12, width = 12, height = 6
        properties = {
          metrics = [
            ["AWS/SQS", "NumberOfMessagesSent", "QueueName", aws_sqs_queue.jobs.name, { label = "sent (API -> queue)" }],
            ["AWS/SQS", "NumberOfMessagesDeleted", "QueueName", aws_sqs_queue.jobs.name, { label = "deleted (processed)" }]
          ]
          view  = "timeSeries", stat = "Sum", period = 60, region = var.aws_region
          title = "Throughput: надходження vs обробка (msg/min)"
        }
      },
      {
        type = "metric", x = 12, y = 12, width = 6, height = 6
        properties = {
          metrics = [["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", aws_sqs_queue.jobs.name]]
          view    = "timeSeries", stat = "Maximum", period = 60, region = var.aws_region
          title   = "Вік найстарішого повідомлення (s)"
        }
      },
      {
        type = "metric", x = 18, y = 12, width = 6, height = 6
        properties = {
          metrics = [["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.jobs_dlq.name]]
          view    = "timeSeries", stat = "Maximum", period = 60, region = var.aws_region
          title   = "Dead-letter queue"
        }
      }
    ]
  })
}
