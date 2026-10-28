resource "aws_ecr_repository" "app_repo" {
  name                 = "notes-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # щоб terraform destroy працював навіть з образами

  image_scanning_configuration {
    scan_on_push = true
  }
}

locals {
  image_tag = substr(sha1(join("", [
    filesha1("${var.app_dir}/Dockerfile"),
    filesha1("${var.app_dir}/requirements.txt"),
    filesha1("${var.app_dir}/main.py"),
    filesha1("${var.app_dir}/models.py"),
    filesha1("${var.app_dir}/database.py"),
  ])), 0, 12)

  app_image = "${aws_ecr_repository.app_repo.repository_url}:${local.image_tag}"
}

# Збирає і пушить образ під час apply, щоб ECS не стартував з неіснуючим образом.
# Потрібні локально: docker і aws cli з налаштованими credentials.
resource "null_resource" "build_and_push" {
  triggers = {
    image = local.app_image
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws ecr get-login-password --region ${var.aws_region} | \
        docker login --username AWS --password-stdin ${aws_ecr_repository.app_repo.registry_id}.dkr.ecr.${var.aws_region}.amazonaws.com
      docker build --platform linux/amd64 -t ${local.app_image} ${var.app_dir}
      docker push ${local.app_image}
    EOT
  }
}
