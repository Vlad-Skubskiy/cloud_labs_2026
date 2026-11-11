locals {
  ecs_dims = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.app.name
  }
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 12
        properties = {
          metrics = [
            ["ECS/ContainerInsights", "DesiredTaskCount", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.app.name],
            ["ECS/ContainerInsights", "RunningTaskCount", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.app.name]
          ]
          view = "timeSeries", stat = "Average", period = 60, region = var.aws_region
          title = "Tasks (desired vs running)"
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 12
        properties = {
          metrics = [["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.app.name]]
          view = "timeSeries", stat = "Average", period = 60, region = var.aws_region
          title = "CPU Utilization (%)"
          annotations = { horizontal = [{ label = "Threshold 70%", value = 70 }] }
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 8, height = 12
        properties = {
          metrics = [["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.main.arn_suffix]]
          view = "timeSeries", stat = "Sum", period = 60, region = var.aws_region
          title = "Requests per minute"
        }
      },
      {
        type = "metric", x = 8, y = 6, width = 8, height = 12
        properties = {
          metrics = [["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.main.arn_suffix]]
          view = "timeSeries", stat = "p95", period = 60, region = var.aws_region
          title = "p95 latency (s)"
        }
      },
      {
        type = "metric", x = 16, y = 6, width = 8, height = 12
        properties = {
          metrics = [["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", aws_lb.main.arn_suffix]]
          view = "timeSeries", stat = "Sum", period = 60, region = var.aws_region
          title = "HTTP 5xx"
        }
      }
    ]
  })
}

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.budget_email
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${var.project_name}-high-cpu"
  alarm_description   = "ECS service CPU >= 70% for 2 minutes"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  dimensions          = local.ecs_dims
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 2
  threshold           = 70
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "latency_high" {
  alarm_name          = "${var.project_name}-high-latency"
  alarm_description   = "ALB p95 latency >= 500ms for 2 minutes"
  namespace           = "AWS/ALB"
  metric_name         = "TargetResponseTime"
  dimensions          = {
    LoadBalancer = aws_lb.main.arn_suffix
  }
  extended_statistic = "p95"
  period              = 60
  evaluation_periods  = 2
  threshold           = 0.5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}