"""
Revoked access tokens.

JWTs are stateless by design (D-012): once signed, a token is valid until it
expires. That is fine for most requests and wrong for logout — "sign out" that
leaves the token usable for eleven more hours is not a sign out.

We keep a denylist rather than a session table because the set is tiny (only
tokens someone logged out of, and only until their natural expiry) and a
Redis TTL expresses "forget this when it could not matter anyway" exactly.

Key: shambatrack:auth:revoked:<jti>, value "1", TTL = remaining lifetime.

**Failure policy: fail open, loudly**, mirroring the login throttle. If Redis
is down, a revoked token would be accepted again for the rest of its life.
Rejecting every token instead would turn a Redis blip into a total outage for
every logged-in user. We choose the smaller blast radius and log it.
"""

import logging

import redis

from app.core.redis_client import redis_client

log = logging.getLogger(__name__)

_KEY_PREFIX = "shambatrack:auth:revoked"


def _key(jti: str) -> str:
    return f"{_KEY_PREFIX}:{jti}"


def revoke(jti: str, ttl_seconds: int) -> None:
    """Revoke one token. A non-positive TTL means it had already expired."""
    if ttl_seconds <= 0:
        return
    try:
        redis_client.setex(_key(jti), ttl_seconds, "1")
    except redis.RedisError as exc:
        log.warning("could not revoke token %s: %s", jti, exc)


def is_revoked(jti: str | None) -> bool:
    if not jti:
        return False
    try:
        return bool(redis_client.exists(_key(jti)))
    except redis.RedisError as exc:
        log.warning("token denylist unavailable, treating token as valid: %s", exc)
        return False
