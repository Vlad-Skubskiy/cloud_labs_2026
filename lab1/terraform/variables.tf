variable "aws_region" {
  type    = string
  default = "eu-central-1"
}

variable "app_dir" {
  description = "Шлях до папки з Dockerfile і кодом застосунку"
  type        = string
  default     = ".."
}

variable "app_port" {
  type    = number
  default = 8000
}

variable "github_repo" {
  type = string
}

variable "project_name" {
  type    = string
  default = "my-app"
}

variable "budget_email" {
  type = string
}
variable "write_mode" {
  description = "async: POST кладе повідомлення в чергу і відповідає 202; sync: запис у БД у тому ж запиті"
  type        = string
  default     = "async"

  validation {
    condition     = contains(["async", "sync"], var.write_mode)
    error_message = "write_mode must be async or sync."
  }
}

variable "queue_max_receive_count" {
  description = "Скільки разів SQS віддасть повідомлення воркеру, перш ніж перекласти його в DLQ"
  type        = number
  default     = 5
}

variable "worker_min_capacity" {
  type    = number
  default = 1
}

variable "worker_max_capacity" {
  type    = number
  default = 5
}

variable "worker_concurrency" {
  description = "Скільки повідомлень один контейнер-обробник обробляє паралельно"
  type        = number
  default     = 4
}

variable "worker_simulated_work_ms" {
  description = "Імітація тривалої операції у воркері (мс). 0 - без імітації."
  type        = number
  default     = 200
}

variable "worker_scale_out_backlog" {
  description = "Довжина черги (visible messages), з якої воркер масштабується вгору"
  type        = number
  default     = 100
}

variable "schedule_timezone" {
  type    = string
  default = "Europe/Kyiv"
}

variable "day_start_cron" {
  description = "Початок «дня» (місцевий час schedule_timezone)"
  type        = string
  default     = "cron(0 8 * * ? *)"
}

variable "night_start_cron" {
  description = "Початок «ночі» (місцевий час schedule_timezone)"
  type        = string
  default     = "cron(0 23 * * ? *)"
}

variable "day_min_capacity" {
  type    = number
  default = 2
}

variable "night_min_capacity" {
  description = "Мінімум екземплярів уночі: 1 або 0. При 0 сервіс повністю зупиняється (ALB віддає 503), доки ранкова дія не підніме його."
  type        = number
  default     = 1
}

variable "schedule_max_capacity" {
  type    = number
  default = 4
}
