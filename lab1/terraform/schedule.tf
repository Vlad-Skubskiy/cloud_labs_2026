resource "aws_appautoscaling_scheduled_action" "day" {
  name               = "${var.project_name}-day"
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  schedule           = var.day_start_cron
  timezone           = var.schedule_timezone

  scalable_target_action {
    min_capacity = var.day_min_capacity
    max_capacity = var.schedule_max_capacity
  }
}

resource "aws_appautoscaling_scheduled_action" "night" {
  name               = "${var.project_name}-night"
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  schedule           = var.night_start_cron
  timezone           = var.schedule_timezone

  scalable_target_action {
    min_capacity = var.night_min_capacity
    max_capacity = var.schedule_max_capacity
  }
}
