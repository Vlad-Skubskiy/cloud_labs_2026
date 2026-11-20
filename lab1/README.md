# Lab 1: Notes API on AWS

A REST API built with FastAPI that stores items in PostgreSQL. Writes go through an SQS queue and are processed by a separate worker; reads of the item list are cached in Redis. The project runs locally with Docker Compose and is deployed to AWS with Terraform: the API and the worker run on ECS Fargate behind an Application Load Balancer, the database runs on RDS, the cache on ElastiCache, and the connection string is stored in AWS Secrets Manager.

## App url:

```
app_url = "http://notes-alb-463991008.eu-north-1.elb.amazonaws.com"
```

## Tech Stack

| Component              | Technology                                                              |
| ---------------------- | ----------------------------------------------------------------------- |
| Language and framework | Python 3.12, FastAPI                                                    |
| ORM                    | SQLAlchemy 2.x                                                          |
| Database               | PostgreSQL 15                                                           |
| Cache / job status     | Redis 7                                                                 |
| Queue                  | Amazon SQS (ElasticMQ locally)                                          |
| Containerization       | Docker, Docker Compose                                                  |
| Infrastructure as code | Terraform >= 1.5                                                        |
| Cloud                  | AWS: VPC, ALB, ECS Fargate, ECR, RDS, ElastiCache, SQS, CloudWatch, SNS, IAM |
| Load testing           | Locust                                                                  |
| CI/CD                  | GitHub Actions, OIDC role                                               |

## Documentation

| Topic | File |
| ----- | ---- |
| Async writes via SQS and the worker | [docs/QUEUE.md](docs/QUEUE.md) |
| Idempotency (`Idempotency-Key`) | [docs/IDEMPOTENCY.md](docs/IDEMPOTENCY.md) |
| Read cache (ElastiCache Redis) | [docs/CACHE.md](docs/CACHE.md) |
| CPU autoscaling of the API | [docs/AUTOSCALING.md](docs/AUTOSCALING.md) |
| Scheduled scaling and cost estimate | [docs/SCHEDULE.md](docs/SCHEDULE.md) |
| Email alerts (CloudWatch → SNS) | [docs/ALERTS.md](docs/ALERTS.md) |
| Load test (Locust) and results | [docs/LOADTEST.md](docs/LOADTEST.md) |

## Project Structure

```
vlad-skubskiy-cloud_labs_2026/
    ├── lab1/
    │   ├── main.py              # FastAPI app: /items, /jobs, /health, /cache/stats
    │   ├── worker.py            # SQS consumer that writes items to PostgreSQL
    │   ├── jobs.py              # SQS client and job status in Redis
    │   ├── idempotency.py       # Idempotency-Key handling
    │   ├── cache.py             # cache-aside for GET /items
    │   ├── redis_client.py
    │   ├── items_repo.py
    │   ├── database.py
    │   ├── models.py
    │   ├── requirements.txt
    │   ├── pytest.ini
    │   ├── Dockerfile
    │   ├── .dockerignore
    │   ├── compose.yaml
    │   ├── tests/
    │   │   └── test_idempotency.py
    │   ├── loadtest/
    │   │   ├── locustfile.py
    │   │   ├── run.sh
    │   │   └── results/         # CSV and HTML report of the last run
    │   ├── docs/                # reports, screenshots in docs/img/
    │   └── terraform/
    │       ├── providers.tf
    │       ├── variables.tf
    │       ├── outputs.tf
    │       ├── network.tf
    │       ├── alb.tf
    │       ├── ecr.tf
    │       ├── ecs.tf
    │       ├── autoscaling.tf
    │       ├── schedule.tf
    │       ├── worker.tf
    │       ├── sqs.tf
    │       ├── elasticache.tf
    │       ├── rds.tf
    │       ├── cloudwatch.tf
    │       ├── queue_dashboard.tf
    │       └── github_oidc.tf
    └── .github/
        └── workflows/
            ├── ci.yml
            └── cd.yml
```

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

   `DATABASE_URL` does not need to be set: Compose assembles it from the `POSTGRES_*` variables.

2. Start the services:

   ```bash
   docker compose up --build
   ```

   This starts `web` (API on http://localhost:8000), `worker`, `db` (PostgreSQL, port 5432), `redis` (port 6379) and `sqs` (ElasticMQ, an SQS-compatible queue; UI on http://localhost:9325). The API and the worker start only after PostgreSQL and Redis pass their health checks. Set `WRITE_MODE=sync` in `.env` to write to the database directly in the request, without the queue.

3. Stop the services (`-v` also deletes the database volume):

   ```bash
   docker compose down
   docker compose down -v
   ```

The application reads its connection string from the `DATABASE_URL` environment variable. If it is not set, startup fails with an error.

### Tests

The tests need a real PostgreSQL and Redis. They use a separate test database so that test rows do not end up in the dev database from Compose:

```bash
docker run -d --rm --name test-pg -p 5433:5432 \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test postgres:15-alpine
docker compose up -d redis

DATABASE_URL=postgresql+psycopg://test:test@localhost:5433/test \
REDIS_URL=redis://localhost:6379/0 pytest -v

docker stop test-pg
```

Details: [docs/IDEMPOTENCY.md](docs/IDEMPOTENCY.md#тест).

## Deploying to AWS

### Requirements

- Terraform >= 1.5.0
- AWS CLI with configured credentials (`aws configure`) and permissions to create the resources listed below
- Docker (the image is built locally and pushed to ECR during `terraform apply`)
- A GitHub repository (needed to configure the OIDC role)

### Steps

Create `terraform/terraform.tfvars` (it is in `.gitignore`):

```hcl
aws_region   = "eu-north-1"
github_repo  = "<owner>/<repo>"
budget_email = "<email for alerts>"
```

```bash
cd terraform
terraform init
terraform apply
```

When it finishes, Terraform prints `app_url`. Confirm the SNS subscription from the first AWS email, otherwise alerts are not delivered.

## Infrastructure Architecture

```
                     Internet
                        |
                        v
        Application Load Balancer   (public subnets, port 80)
                        |
                        v
        ECS service notes-service   (private subnets, port 8000, 1-4 tasks)
           |            |             |
           |  SendMessage            GET/SET
           v            |             v
     SQS notes-jobs     |       ElastiCache Redis   (port 6379)
      (+ DLQ)           |             ^
           |            |             | job status, cache version
           v            |             |
   ECS service notes-worker-service --+   (private subnets, 1-5 tasks)
           |            |
           v            v
        RDS PostgreSQL 15          (private subnets, port 5432)
```

### Networking

- VPC `10.0.0.0/16` with DNS support and DNS hostnames enabled.
- Two public subnets (for the ALB and NAT Gateway) and two private subnets (for ECS, RDS and ElastiCache) in zones `a` and `b` of the selected region.
- An Internet Gateway for the public subnets.
- A single NAT Gateway in the first public subnet. Private subnets reach the internet through it (needed, for example, to pull the image from ECR, ship logs and call SQS).

### Security

Access between components is restricted with security groups. The API and the worker share `notes-ecs-sg`:

| Security group   | Inbound traffic                    |
| ---------------- | ---------------------------------- |
| `notes-alb-sg`   | TCP 80 from anywhere (`0.0.0.0/0`) |
| `notes-ecs-sg`   | TCP 8000 only from `notes-alb-sg`  |
| `notes-rds-sg`   | TCP 5432 only from `notes-ecs-sg`  |
| `notes-redis-sg` | TCP 6379 only from `notes-ecs-sg`  |

The database is not publicly accessible (`publicly_accessible = false`). The container runs as the unprivileged user `appuser`. The API task role may only send to the `notes-jobs` queue; the worker task role may only receive and delete from it.

### Secrets

- The database password is generated by `random_password` (16 characters).
- The full connection string is stored in Secrets Manager (secret `notes-api-database-url`).
- ECS injects the secret into the API and worker containers as the `DATABASE_URL` environment variable. The `secretsmanager:GetSecretValue` permission is granted only to the task execution role and only for this secret.

## Terraform Variables

| Variable                   | Type   | Default              | Description |
| -------------------------- | ------ | -------------------- | ----------- |
| `aws_region`               | string | `eu-central-1`       | AWS region (the deployment uses `eu-north-1` from `terraform.tfvars`) |
| `project_name`             | string | `notes`              | Prefix for cluster, queue, alarm and SNS names |
| `app_dir`                  | string | `..`                 | Path to the folder containing the Dockerfile and application code |
| `app_port`                 | number | `8000`               | Application port inside the container |
| `github_repo`              | string | none (required)      | Repository in `owner/repo` format, used for the OIDC trust policy |
| `budget_email`             | string | none (required)      | Email subscribed to the `notes-alerts` SNS topic |
| `write_mode`               | string | `async`              | `async`: `POST /items` goes through the queue; `sync`: direct write |
| `queue_max_receive_count`  | number | `5`                  | Receives before a message moves to the DLQ |
| `worker_min_capacity`      | number | `1`                  | Minimum worker tasks |
| `worker_max_capacity`      | number | `5`                  | Maximum worker tasks |
| `worker_concurrency`       | number | `4`                  | Messages one worker processes in parallel |
| `worker_simulated_work_ms` | number | `200`                | Simulated processing time per message (0 = off) |
| `worker_scale_out_backlog` | number | `100`                | Queue length at which the worker scales out |
| `schedule_timezone`        | string | `Europe/Kyiv`        | Time zone for scheduled scaling |
| `day_start_cron`           | string | `cron(0 8 * * ? *)`  | Start of the "day" schedule |
| `night_start_cron`         | string | `cron(0 23 * * ? *)` | Start of the "night" schedule |
| `day_min_capacity`         | number | `2`                  | Minimum API tasks during the day |
| `night_min_capacity`       | number | `1`                  | Minimum API tasks at night (can be 0) |
| `schedule_max_capacity`    | number | `4`                  | Maximum API tasks set by both scheduled actions |

## Terraform Outputs

| Output                    | Description                            |
| ------------------------- | -------------------------------------- |
| `app_url`                 | Public application URL (ALB DNS name)  |
| `ecr_repository_url`      | ECR repository URL                     |
| `github_actions_role_arn` | ARN of the IAM role for GitHub Actions |

## CI/CD with GitHub Actions

- **CI** ([ci.yml](../.github/workflows/ci.yml)) runs on pull requests and pushes to branches other than `main`: idempotency tests against real PostgreSQL and Redis service containers, an API smoke test, a Docker build check (the process must not run as root), a Compose run that writes through the queue and checks the data survives a restart, and `terraform fmt` / `validate`.
- **CD** ([cd.yml](../.github/workflows/cd.yml)) runs on pushes to `main` that change application code: it runs CI, builds the image tagged with the commit SHA, pushes it to ECR and deploys new task definitions to `notes-worker-service` and `notes-service` in the `notes-cluster` cluster.

Terraform creates everything needed to deploy from GitHub Actions without long-lived access keys:

- An OIDC provider for `token.actions.githubusercontent.com`.
- The IAM role, which can be assumed only from the `main` branch of the repository given in `github_repo`. Its ARN goes into the `AWS_ROLE_ARN` repository variable.
- Minimal role permissions: ECR login and image push to the `notes-api` repository, task definition registration, updates to the `notes-service` and `notes-worker-service` services, and `iam:PassRole` only for the ECS execution role and the two task roles.

## Cleanup

```bash
cd terraform
terraform destroy
```
