# Lab 1: Notes API on AWS

A REST API built with FastAPI that stores data in PostgreSQL. The project can be run locally with Docker Compose and deployed to AWS with Terraform: the container runs on ECS Fargate behind an Application Load Balancer, the database runs on RDS, and the connection string is stored in AWS Secrets Manager.

## Tech Stack

| Component              | Technology                                                             |
| ---------------------- | ---------------------------------------------------------------------- |
| Language and framework | Python 3.12, FastAPI, Uvicorn                                          |
| ORM                    | SQLAlchemy 2.x (psycopg driver)                                        |
| Database               | PostgreSQL 15                                                          |
| Containerization       | Docker, Docker Compose                                                 |
| Infrastructure as code | Terraform >= 1.5 (aws, random, null providers)                         |
| Cloud                  | AWS: VPC, ALB, ECS Fargate, ECR, RDS, Secrets Manager, CloudWatch, IAM |

## Project Structure

```
lab1/
├── compose.yaml          # Local run: application + PostgreSQL
├── Dockerfile            # Application image
├── .dockerignore
├── requirements.txt      # Python dependencies
├── main.py               # FastAPI endpoints
├── database.py           # Database connection (SQLAlchemy)
├── models.py             # Item model
└── terraform/
    ├── providers.tf      # Providers and versions
    ├── variables.tf      # Input variables
    ├── network.tf        # VPC, subnets, IGW, NAT, routing
    ├── alb.tf            # Application Load Balancer, target group, listener
    ├── ecr.tf            # ECR repository, image build and push
    ├── ecs.tf            # Cluster, task definition, service, IAM roles
    ├── rds.tf            # RDS PostgreSQL, password, secret with DATABASE_URL
    ├── github_oidc.tf    # OIDC provider and role for GitHub Actions
    └── outputs.tf        # Output values
```

## API

| Method | Path                              | Description                                                                      |
| ------ | --------------------------------- | -------------------------------------------------------------------------------- |
| GET    | `/health`                         | Health check, returns `{"status": "ok"}`. Used by the load balancer health check |
| GET    | `/items`                          | List all items                                                                   |
| POST   | `/items?name=...&description=...` | Create an item. `name` is required, `description` is optional                    |

POST parameters are passed via the query string. The `items` table is created automatically when the application starts (`create_all`).

`Item` model:

| Field       | Type    | Notes       |
| ----------- | ------- | ----------- |
| id          | Integer | Primary key |
| name        | String  | Indexed     |
| description | String  | Nullable    |

Interactive documentation is available at `/docs` (Swagger UI).

## Running Locally

### Requirements

- Docker and Docker Compose

### Steps

1. Create a `.env` file next to `compose.yaml`:

   ```env
   POSTGRES_USER=notes
   POSTGRES_PASSWORD=notes_password
   POSTGRES_DB=notes
   ```

2. Start the services:

   ```bash
   docker compose up --build
   ```

   The application starts only after PostgreSQL passes its health check (`pg_isready`).

3. Verify that it works:

   ```bash
   curl http://localhost:8000/health
   curl -X POST "http://localhost:8000/items?name=test&description=first"
   curl http://localhost:8000/items
   ```

4. Stop the services:

   ```bash
   docker compose down        # keep data
   docker compose down -v     # also remove the postgres_data volume
   ```

The application reads its connection string from the `DATABASE_URL` environment variable. If it is not set, startup fails with an error. In Compose it is assembled automatically from the `POSTGRES_*` variables.

## Deploying to AWS

### Requirements

- Terraform >= 1.5.0
- AWS CLI with configured credentials (`aws configure`) and permissions to create the resources listed below
- Docker (the image is built locally during `terraform apply`)
- A GitHub repository (needed to configure the OIDC role)

### Steps

```bash
cd terraform
terraform init
terraform apply -var="github_repo=<owner>/<repo>"
```

During `apply` the following happens:

1. The network, load balancer, ECR repository, database, and secret are created.
2. The `null_resource.build_and_push` resource logs in to ECR, builds the image for `linux/amd64`, and pushes it with the `bootstrap` tag.
3. The task definition and ECS service are created, and the service starts a container from that image.

When it finishes, Terraform prints `app_url`. To verify:

```bash
curl $(terraform output -raw app_url)/health
```

The first run may take several minutes: RDS and the NAT Gateway are not created instantly, and the ECS service has `health_check_grace_period_seconds = 60`.

## Infrastructure Architecture

```
Internet
   |
   v
Application Load Balancer  (public subnets, port 80)
   |
   v
ECS Fargate service        (private subnets, port 8000)
   |
   v
RDS PostgreSQL 15          (private subnets, port 5432)
```

### Networking

- VPC `10.0.0.0/16` with DNS support and DNS hostnames enabled.
- Two public subnets (for the ALB and NAT Gateway) and two private subnets (for ECS and RDS) in zones `a` and `b` of the selected region.
- An Internet Gateway for the public subnets.
- A single NAT Gateway in the first public subnet. Private subnets reach the internet through it (needed, for example, to pull the image from ECR and ship logs).

### Security

Access between components is restricted with security groups:

| Security group | Inbound traffic                    |
| -------------- | ---------------------------------- |
| `notes-alb-sg` | TCP 80 from anywhere (`0.0.0.0/0`) |
| `notes-ecs-sg` | TCP 8000 only from `notes-alb-sg`  |
| `notes-rds-sg` | TCP 5432 only from `notes-ecs-sg`  |

The database is not publicly accessible (`publicly_accessible = false`). The container runs as the unprivileged user `appuser`.

### Secrets

- The database password is generated by `random_password` (16 characters).
- The full connection string is stored in Secrets Manager (secret `notes-api-database-url`).
- ECS injects the secret into the container as the `DATABASE_URL` environment variable. The `secretsmanager:GetSecretValue` permission is granted only to the task execution role and only for this secret.

### Compute

- Fargate task: 0.25 vCPU (`cpu = 256`), 512 MB memory, a single instance (`desired_count = 1`).
- Logs are sent to CloudWatch Logs, log group `/ecs/notes-api`.
- Target group health check: `GET /health`, expects status 200, 30-second interval.

### Database

- RDS PostgreSQL 15.17, instance class `db.t3.micro`.
- 20 GB of storage with autoscaling up to 100 GB.
- Database name `notes`, user `dbadmin`.
- `skip_final_snapshot = true`: no snapshot is taken when the instance is deleted.

## Terraform Variables

| Variable      | Type   | Default         | Description                                                       |
| ------------- | ------ | --------------- | ----------------------------------------------------------------- |
| `aws_region`  | string | `eu-central-1`  | AWS region                                                        |
| `app_dir`     | string | `..`            | Path to the folder containing the Dockerfile and application code |
| `app_port`    | number | `8000`          | Application port inside the container                             |
| `github_repo` | string | none (required) | Repository in `owner/repo` format, used for the OIDC trust policy |

## Terraform Outputs

| Output                    | Description                            |
| ------------------------- | -------------------------------------- |
| `app_url`                 | Public application URL (ALB DNS name)  |
| `ecr_repository_url`      | ECR repository URL                     |
| `github_actions_role_arn` | ARN of the IAM role for GitHub Actions |

## CI/CD with GitHub Actions

Terraform creates everything needed to deploy from GitHub Actions without long-lived access keys:

- An OIDC provider for `token.actions.githubusercontent.com`.
- The IAM role `notes-github-actions-deploy`, which can be assumed only from the `main` branch of the repository given in `github_repo`.
- Minimal role permissions: ECR login and image push to the `notes-api` repository, task definition registration, updates to the `notes-service` service, and `iam:PassRole` only for the ECS execution role.

The ECS service uses `ignore_changes = [task_definition]`, so new task definition revisions registered by the pipeline are not reverted by a subsequent `terraform apply`.

The workflow file itself is not part of this repository. To set it up, take the `github_actions_role_arn` output and use it in the `aws-actions/configure-aws-credentials` step as `role-to-assume`. The workflow must also grant the `id-token: write` and `contents: read` permissions.

## Cleanup

```bash
cd terraform
terraform destroy -var="github_repo=<owner>/<repo>"
```

The ECR repository is created with `force_delete = true`, the secret is deleted without a recovery window, and RDS has the final snapshot disabled, so all data is permanently deleted. Remember to run `destroy` after you finish testing: the NAT Gateway, ALB, and RDS are billed hourly.

## Known Limitations

This is a learning project, so several decisions are simplified:

- The load balancer accepts only HTTP (port 80); HTTPS is not configured.
- There is a single NAT Gateway and a single task instance, so there is no high availability.
- The log group uses `retention_in_days = 0`, which means logs are kept indefinitely.
- The database schema is created with `create_all`; migrations (for example, Alembic) are not used.
- `requirements.txt` includes packages the application itself does not need (for example, `awscli` and `psycopg2-binary`), which could be removed to reduce the image size.
