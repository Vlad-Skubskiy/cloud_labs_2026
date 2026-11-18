import os

import redis


class ServiceUnavailable(Exception):
    pass


_client: redis.Redis | None = None


def get() -> redis.Redis:
    global _client
    if _client is None:
        url = os.getenv("REDIS_URL")
        if not url:
            raise ServiceUnavailable("REDIS_URL is not configured")
        _client = redis.Redis.from_url(
            url,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
            max_connections=50,
        )
    return _client
