import json
import logging
import os
import random
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cache
import items_repo
import jobs
import models
from database import SessionLocal, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")

MAX_RECEIVES = int(os.getenv("MAX_RECEIVE_COUNT", "5"))
CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "4"))
WAIT_SECONDS = int(os.getenv("WORKER_WAIT_SECONDS", "3"))
SIMULATED_WORK_MS = int(os.getenv("WORKER_SIMULATED_WORK_MS", "0"))
CHAOS_RATE = float(os.getenv("WORKER_CHAOS_RATE", "0"))

stop = threading.Event()


class ChaosError(Exception):
    pass


def process_job(job: dict) -> tuple[int, bool]:
    if SIMULATED_WORK_MS:
        time.sleep(SIMULATED_WORK_MS / 1000)
    with SessionLocal() as db:
        item_id, created = items_repo.insert_item(
            db, job["name"], job.get("description"), dedupe_id=job["job_id"]
        )
    if created:
        cache.bump_version()
    return item_id, created


def _best_effort_update(job_id: str, **fields) -> None:
    try:
        jobs.update(job_id, **fields)
    except Exception as exc:
        log.warning("job status update failed: %s", exc)


def handle_message(msg: dict) -> bool:
    receive_count = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
    try:
        job = json.loads(msg["Body"])
        job_id = job["job_id"]
    except (ValueError, KeyError, TypeError):
        log.error("malformed message, leaving it for redelivery/DLQ: %.200s", msg.get("Body"))
        return False

    try:
        jobs.update(job_id, status="processing", attempts=receive_count)
        item_id, created = process_job(job)
        if CHAOS_RATE and random.random() < CHAOS_RATE:
            raise ChaosError("simulated crash after commit, before ack")
        jobs.update(job_id, status="done", item_id=item_id, attempts=receive_count, error=None)
        log.info("job %s done item=%s created=%s attempt=%s", job_id, item_id, created, receive_count)
        return True
    except Exception as exc:
        final = receive_count >= MAX_RECEIVES
        log.exception("job %s failed (attempt %s/%s)", job_id, receive_count, MAX_RECEIVES)
        _best_effort_update(
            job_id,
            status="failed" if final else "retrying",
            attempts=receive_count,
            error=str(exc)[:300],
        )
        return False


def run() -> None:
    models.ensure_schema(engine)
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    client = jobs.sqs_client(read_timeout=WAIT_SECONDS + 20)
    url = None
    while url is None and not stop.is_set():
        try:
            url = jobs.queue_url()
        except Exception as exc:
            log.warning("queue not ready yet: %s", exc)
            time.sleep(2)

    log.info("worker started: queue=%s concurrency=%s work_ms=%s chaos=%s",
             url, CONCURRENCY, SIMULATED_WORK_MS, CHAOS_RATE)
    pool = ThreadPoolExecutor(max_workers=CONCURRENCY)

    while not stop.is_set():
        try:
            resp = client.receive_message(
                QueueUrl=url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=WAIT_SECONDS,
                AttributeNames=["ApproximateReceiveCount"],
            )
            messages = resp.get("Messages", [])
            if not messages:
                continue
            results = list(pool.map(handle_message, messages))
            entries = [
                {"Id": str(i), "ReceiptHandle": m["ReceiptHandle"]}
                for i, (m, ok) in enumerate(zip(messages, results))
                if ok
            ]
            if entries:
                client.delete_message_batch(QueueUrl=url, Entries=entries)
        except Exception as exc:
            log.error("poll loop error: %s", exc)
            time.sleep(2)

    log.info("SIGTERM received, current batch finished, shutting down")
    pool.shutdown(wait=True)


if __name__ == "__main__":
    run()
