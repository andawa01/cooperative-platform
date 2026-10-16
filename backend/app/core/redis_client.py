"""
Redis client.

One connection pool, shared across the app. Redis is used for the SMS
dispatch pipeline (queue + retry state), NOT for durable data — see D-024.

We expose the raw client as `redis_client` and provide a healthcheck
helper for the `/health/redis` endpoint.
"""
import redis

from app.core.config import settings


# decode_responses=True so values come back as Python str, not bytes.
# Slightly slower, much friendlier.
# BRPOP_TIMEOUT is how long we block-wait for a queue item each loop tick.
# socket_timeout must be strictly greater than this so the underlying socket
# doesn't raise a read-timeout error during a legitimate blocking pop.
# socket_connect_timeout is separate — it only applies to the initial TCP
# handshake, so 2 s is fine there.
BRPOP_TIMEOUT = 5  # seconds — must match the timeout arg in brpop() calls
_SOCKET_TIMEOUT = BRPOP_TIMEOUT + 10  # gives 10 s of headroom beyond the pop

redis_client: redis.Redis = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=_SOCKET_TIMEOUT,
)


def ping() -> bool:
    """Return True if Redis responds to PING. Used by the health endpoint."""
    try:
        return redis_client.ping() is True
    except redis.RedisError:
        return False