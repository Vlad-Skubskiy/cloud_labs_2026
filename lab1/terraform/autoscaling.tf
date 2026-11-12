# NOTE: remove `aws_appautoscaling_target.ecs_target` and
# `aws_appautoscaling_policy.ecs_policy` from ecs.tf - they now live here.
# The target keeps the same resource address, so Terraform state is unchanged.

resource "aws_appautoscaling_target" "ecs_target" {
  max_capacity       = 4
  min_capacity       = 2
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.app.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# ---------- scale out ----------
# Target tracking always waits for 3 consecutive 1-minute datapoints (>= 3 min)
# and its alarm cannot be tuned. Step scaling lets the alarm fire on 1 datapoint.
resource "aws_appautoscaling_policy" "scale_out" {
  name               = "step-scale-out"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    metric_aggregation_type = "Average"
    cooldown                = 60

    # bounds are relative to the alarm threshold (60%)
    step_adjustment {
      metric_interval_lower_bound = 0
      metric_interval_upper_bound = 20 # CPU 60..80% -> +1 task
      scaling_adjustment          = 1
    }
    step_adjustment {
      metric_interval_lower_bound = 20 # CPU >= 80% -> +2 tasks
      scaling_adjustment          = 2
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "scale_out_cpu" {
  alarm_name          = "${var.project_name}-scale-out-cpu"
  alarm_description   = "ECS CPU >= 60% for 1 minute -> add tasks"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  dimensions          = local.ecs_dims
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 1 # raise to 2 if you see flapping
  threshold           = 60
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.scale_out.arn]
}

# ---------- scale in ----------
resource "aws_appautoscaling_policy" "scale_in" {
  name               = "step-scale-in"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    metric_aggregation_type = "Average"
    cooldown                = 300

    step_adjustment {
      metric_interval_upper_bound = 0 # CPU below the alarm threshold -> -1 task
      scaling_adjustment          = -1
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "scale_in_cpu" {
  alarm_name          = "${var.project_name}-scale-in-cpu"
  alarm_description   = "ECS CPU < 30% for 10 minutes -> remove a task"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  dimensions          = local.ecs_dims
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 10
  threshold           = 30
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.scale_in.arn]
}
