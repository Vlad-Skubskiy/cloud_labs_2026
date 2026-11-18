import hashlib
import json
import os

import redis_client

TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", str(24 * 3600)))
PROCESSING_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_PROCESSING_TTL_SECONDS", "60"))


class KeyReuseMismatch(Exception):
    pass


class RequestInProgress(Exception):
    pass


def fingerprint(**params) -> str:
    raw = json.dumps(params, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _rkey(scope: str, key: str) -> str:
    return f"idem:{scope}:{key}"


def begin(scope: str, key: str, fp: str) -> dict | None:
    r = redis_client.get()
    rkey = _rkey(scope, key)
    for _ in range(3):
        claimed = r.set(
            rkey,
            json.dumps({"state": "processing", "fp": fp}),
            nx=True,
            ex=PROCESSING_TTL_SECONDS,
        )
        if claimed:
            return None
        raw = r.get(rkey)
        if raw is None:
            continue
        record = json.loads(raw)
        if record["fp"] != fp:
            raise KeyReuseMismatch()
        if record["state"] == "processing":
            raise RequestInProgress()
        return record
    raise RequestInProgress()


def complete(scope: str, key: str, fp: str, status: int, body: dict, headers: dict) -> None:
    redis_client.get().set(
        _rkey(scope, key),
        json.dumps(
            {"state": "done", "fp": fp, "status": status, "body": body, "headers": headers},
            ensure_ascii=False,
        ),
        ex=TTL_SECONDS,
    )


def abort(scope: str, key: str) -> None:
    redis_client.get().delete(_rkey(scope, key))
