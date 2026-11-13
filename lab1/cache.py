import logging
import os
import random
 
import redis
 
log = logging.getLogger("cache")
 
REDIS_URL = os.getenv("REDIS_URL")
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "30"))
INVALIDATE_ON_WRITE = os.getenv("CACHE_INVALIDATE_ON_WRITE", "false").lower() == "true"
 
_client = None
if CACHE_ENABLED and REDIS_URL:
    _client = redis.Redis.from_url(
        REDIS_URL,
        socket_timeout=0.25,
        socket_connect_timeout=0.25,
        max_connections=50,
    )
 
_VERSION_KEY = "items:version"
_STAT_PREFIX = "cache:stat:"
 
 
def enabled() -> bool:
    return _client is not None
 
 
def version() -> str:
    if _client is None or not INVALIDATE_ON_WRITE:
        return "0"
    try:
        value = _client.get(_VERSION_KEY)
        return value.decode() if value else "0"
    except redis.RedisError as exc:
        log.warning("cache version read failed: %s", exc)
        return "0"
 
 
def bump_version() -> None:
    if _client is None or not INVALIDATE_ON_WRITE:
        return
    try:
        _client.incr(_VERSION_KEY)
    except redis.RedisError as exc:
        log.warning("cache version bump failed: %s", exc)
 
 
def cache_get(key: str) -> bytes | None:
    if _client is None:
        return None
    try:
        return _client.get(key)
    except redis.RedisError as exc:
        log.warning("cache get failed: %s", exc)
        return None
 
 
def cache_set(key: str, value: bytes) -> None:
    if _client is None:
        return

    ttl = CACHE_TTL + random.randint(0, max(1, CACHE_TTL // 10))
    try:
        _client.set(key, value, ex=ttl)
    except redis.RedisError as exc:
        log.warning("cache set failed: %s", exc)
 
 
def record(hit: bool) -> None:

    if _client is None:
        return
    try:
        _client.incr(_STAT_PREFIX + ("hits" if hit else "misses"))
    except redis.RedisError:
        pass
 
 
def stats() -> dict:
    if _client is None:
        return {"enabled": False}
    try:
        hits = int(_client.get(_STAT_PREFIX + "hits") or 0)
        misses = int(_client.get(_STAT_PREFIX + "misses") or 0)
    except redis.RedisError as exc:
        return {"enabled": True, "error": str(exc)}
    total = hits + misses
    return {
        "enabled": True,
        "ttl_seconds": CACHE_TTL,
        "invalidate_on_write": INVALIDATE_ON_WRITE,
        "hits": hits,
        "misses": misses,
        "hit_ratio": round(hits / total, 4) if total else None,
    }
 
 
def reset_stats() -> None:
    if _client is None:
        return
    try:
        _client.delete(_STAT_PREFIX + "hits", _STAT_PREFIX + "misses")
    except redis.RedisError:
        pass