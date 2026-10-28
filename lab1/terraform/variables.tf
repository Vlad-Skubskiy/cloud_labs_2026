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
