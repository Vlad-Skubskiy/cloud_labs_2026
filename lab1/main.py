import logging
import os
import uuid

import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, TypeAdapter
from sqlalchemy.orm import Session

import cache
import idempotency
import items_repo
import jobs
import models
import redis_client
from database import SessionLocal, engine

log = logging.getLogger("api")

models.ensure_schema(engine)

WRITE_MODE = os.getenv("WRITE_MODE", "async").lower()
IDEMPOTENCY_SCOPE = "POST:/items"

app = FastAPI()


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    description: str | None = None


_items_adapter = TypeAdapter(list[ItemOut])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.exception_handler(redis_client.ServiceUnavailable)
@app.exception_handler(redis.RedisError)
async def dependency_unavailable(request: Request, exc: Exception):
    log.error("dependency unavailable: %s", exc)
    return JSONResponse({"detail": "Dependency unavailable, retry later"}, status_code=503,
                        headers={"Retry-After": "1"})


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/items", response_model=list[ItemOut])
def get_items(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
              nocache: bool = False, db: Session = Depends(get_db)):
    use_cache = cache.enabled() and not nocache
    key = f"items:v{cache.version()}:list:{limit}:offset:{offset}" if use_cache else None

    if use_cache:
        cached = cache.cache_get(key)
        if cached is not None:
            cache.record(hit=True)
            return Response(cached, media_type="application/json", headers={"X-Cache": "HIT"})
    rows = (
        db.query(models.Item)
        .order_by(models.Item.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    payload = _items_adapter.dump_json(_items_adapter.validate_python(rows))

    if use_cache:
        cache.cache_set(key, payload)
        cache.record(hit=False)
    return Response(payload, media_type="application/json",
                    headers={"X-Cache": "MISS" if use_cache else "BYPASS"})


@app.get("/items/{item_id}", response_model=ItemOut)
def get_item_by_id(item_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


def _execute_write(name: str, description: str | None, db: Session, key: str | None):
    job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"idempotency:{key}")) if key else None

    if WRITE_MODE == "sync":
        item_id, _ = items_repo.insert_item(db, name, description, dedupe_id=job_id)
        cache.bump_version()
        return 200, {"id": item_id, "name": name, "description": description}, {}

    job_id = job_id or str(uuid.uuid4())
    jobs.create(job_id)
    jobs.enqueue({"job_id": job_id, "name": name, "description": description})
    status_url = f"/jobs/{job_id}"
    return 202, {"job_id": job_id, "status": "queued", "status_url": status_url}, {"Location": status_url}


@app.post("/items", status_code=202, responses={
    200: {"description": "WRITE_MODE=sync: запис виконано одразу"},
    202: {"description": "Прийнято в обробку; статус - за Location / status_url"},
    409: {"description": "Запит із цим Idempotency-Key ще виконується"},
    422: {"description": "Idempotency-Key повторно використано з іншими параметрами"},
    503: {"description": "Redis/черга недоступні"},
})
def post_item(
    name: str,
    description: str | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    if idempotency_key is None:
        status, body, headers = _execute_write(name, description, db, None)
        return JSONResponse(body, status_code=status, headers=headers)

    key = idempotency_key.strip()
    if not (1 <= len(key) <= 255) or not key.isprintable():
        raise HTTPException(status_code=400, detail="Idempotency-Key must be 1-255 printable characters")

    fp = idempotency.fingerprint(name=name, description=description)
    try:
        stored = idempotency.begin(IDEMPOTENCY_SCOPE, key, fp)
    except idempotency.KeyReuseMismatch:
        raise HTTPException(status_code=422, detail="Idempotency-Key was already used with different parameters")
    except idempotency.RequestInProgress:
        raise HTTPException(status_code=409, detail="A request with this Idempotency-Key is still in progress",
                            headers={"Retry-After": "1"})

    if stored is not None:
        return JSONResponse(stored["body"], status_code=stored["status"],
                            headers={**stored["headers"], "Idempotent-Replay": "true"})

    try:
        status, body, headers = _execute_write(name, description, db, key)
    except BaseException:
        try:
            idempotency.abort(IDEMPOTENCY_SCOPE, key)
        except Exception as exc:
            log.warning("idempotency abort failed: %s", exc)
        raise

    try:
        idempotency.complete(IDEMPOTENCY_SCOPE, key, fp, status, body, headers)
    except redis.RedisError as exc:
        log.warning("idempotency complete failed: %s", exc)
    return JSONResponse(body, status_code=status, headers=headers)


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found (unknown id or older than 24h)")
    if job.get("status") == "done" and job.get("item_id") is not None:
        job["result_url"] = f"/items/{job['item_id']}"
    return job


@app.get("/cache/stats")
def cache_stats():
    return cache.stats()


@app.delete("/cache/stats")
def cache_stats_reset():
    cache.reset_stats()
    return {"status": "reset"}
