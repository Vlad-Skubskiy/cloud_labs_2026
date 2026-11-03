output "app_url" {
  description = "Публічна адреса застосунку"
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app_repo.repository_url
}

# output "github_actions_role_arn" {
#   description = "ARN ролі для GitHub Actions"
#   value       = aws_iam_role.github_actions.arn
# }
