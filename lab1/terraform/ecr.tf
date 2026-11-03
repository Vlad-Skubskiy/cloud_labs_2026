resource "aws_ecr_repository" "app_repo" {
  name                 = "notes-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true 

  image_scanning_configuration {
    scan_on_push = true
  }
}

locals {
  app_image = "${aws_ecr_repository.app_repo.repository_url}:bootstrap"
}

resource "null_resource" "build_and_push" {
  triggers = {
    repository = aws_ecr_repository.app_repo.repository_url
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
