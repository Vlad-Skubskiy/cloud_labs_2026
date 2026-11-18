import json
import logging
import os
import time

import redis_client

log = logging.getLogger("jobs")

JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", str(24 * 3600)))
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
SQS_QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "notes-jobs")
SQS_ENDPOINT_URL = os.getenv("SQS_ENDPOINT_URL")
SQS_AUTO_CREATE = os.getenv("SQS_AUTO_CREATE", "false").lower() == "true"

_clients: dict[int, object] = {}
_queue_url: str | None = None


def sqs_client(read_timeout: int = 5):
    if read_timeout not in _clients:
        import boto3
        from botocore.config import Config

        _clients[read_timeout] = boto3.client(
            "sqs",
            region_name=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
            endpoint_url=SQS_ENDPOINT_URL,
            config=Config(
                connect_timeout=2,
                read_timeout=read_timeout,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
    return _clients[read_timeout]


def queue_url() -> str:
    global _queue_url
    if SQS_QUEUE_URL:
        return SQS_QUEUE_URL
    if _queue_url is None:
        from botocore.exceptions import ClientError

        client = sqs_client()
        try:
            _queue_url = client.get_queue_url(QueueName=SQS_QUEUE_NAME)["QueueUrl"]
        except ClientError:
            if not SQS_AUTO_CREATE:
                raise
            _queue_url = client.create_queue(
                QueueName=SQS_QUEUE_NAME,
                Attributes={"VisibilityTimeout": "60"},
            )["QueueUrl"]
    return _queue_url


def _jkey(job_id: str) -> str:
    return f"job:{job_id}"


def create(job_id: str) -> None:
    redis_client.get().set(
        _jkey(job_id),
        json.dumps({"job_id": job_id, "status": "queued", "attempts": 0, "created_at": time.time()}),
        nx=True,
        ex=JOB_TTL_SECONDS,
    )


def get(job_id: str) -> dict | None:
    raw = redis_client.get().get(_jkey(job_id))
    return json.loads(raw) if raw else None


def update(job_id: str, **fields) -> None:
    job = get(job_id) or {"job_id": job_id, "created_at": time.time()}
    job.update(fields, updated_at=time.time())
    redis_client.get().set(_jkey(job_id), json.dumps(job), ex=JOB_TTL_SECONDS)


def enqueue(payload: dict) -> None:
    try:
        sqs_client().send_message(QueueUrl=queue_url(), MessageBody=json.dumps(payload))
    except Exception as exc:
        log.error("enqueue failed: %s", exc)
        raise redis_client.ServiceUnavailable("queue is unavailable") from exc
