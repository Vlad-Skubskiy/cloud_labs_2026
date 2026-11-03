resource "aws_db_subnet_group" "main" {
  name       = "notes-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "notes-db-subnet-group"
  }
}

resource "aws_security_group" "rds_sg" {
  name   = "notes-rds-sg"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "notes-rds-sg"
  }
}

resource "random_password" "db_password" {
  length  = 16
  special = false 
}


resource "aws_db_instance" "postgres" {
  identifier     = "notes-db"
  engine         = "postgres"
  engine_version = "15.17"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 100

  db_name  = "notes"
  username = "dbadmin"
  password = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]

  publicly_accessible = false 
  skip_final_snapshot = true
}

resource "aws_secretsmanager_secret" "database_url" {
  name                    = "notes-api-database-url"
  recovery_window_in_days = 0 
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id

  secret_string = "postgresql://${aws_db_instance.postgres.username}:${random_password.db_password.result}@${aws_db_instance.postgres.endpoint}/${aws_db_instance.postgres.db_name}"
}