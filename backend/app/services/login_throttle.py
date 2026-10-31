"""
Login throttling.

Baseline: `LOGIN_MAX_ATTEMPTS` failures per `LOGIN_WINDOW_SECONDS` for an
email address locks that account for `LOGIN_LOCKOUT_SECONDS`. Successive
lockouts for the same email double, capped at a day, so a sustained attacker's
cost grows while a clerk who fat-fingered five times waits one window.

**Scoped to the account, deliberately not to the client IP.**

In-app IP limiting looks reasonable and is wrong here:

- Behind a load balancer `request.client.host` is the balancer, so five bad
  passwords would lock out every user of the cooperative at once.
- Even without a proxy, a rural office or cybercafé shares one NAT address;
  one person mistyping must not stop their colleagues from working.

Spraying a single password across many accounts is a real attack, but it is
the wrong shape for this layer: it needs to see true client addresses and
volumetrics, which belongs at the reverse proxy / WAF. This table protects an
account from being ground down, which is the attack we can see and bound here.

**Failure policy: fail open, loudly.** If Redis is unreachable the attempt is
allowed and a warning is logged. Locking every user out of the system because
the throttling store is down is worse than briefly losing throttling, and an
auth outage is a bigger prize than a slower brute force.

Identifiers are hashed into the key: a Redis dump should not be a list of
staff email addresses, and an email containing `:` must not forge a key shape.
"""

import hashlib
import logging
from dataclasses import dataclass

import redis

from app.core.config import settings
from app.core.redis_client import redis_client

log = logging.getLogger(__name__)

_KEY_PREFIX = "shambatrack:login"
_ESCALATION_TTL = 24 * 60 * 60  # forget a lockout history after a day


@dataclass(frozen=True)
class ThrottleState:
    limited: bool
    retry_after: int = 0  # seconds until the caller may try again


def _digest(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:32]


def _fail_key(email: str) -> str:
    return f"{_KEY_PREFIX}:fail:{_digest(email)}"


def _lock_key(email: str) -> str:
    return f"{_KEY_PREFIX}:lock:{_digest(email)}"


def _escalation_key(email: str) -> str:
    return f"{_KEY_PREFIX}:lockouts:{_digest(email)}"


def _unavailable(exc: Exception) -> ThrottleState:
    log.warning("login throttle unavailable, allowing attempt: %s", exc)
    return ThrottleState(limited=False)


def check(email: str) -> ThrottleState:
    """Is this account currently locked out?"""
    try:
        ttl = redis_client.ttl(_lock_key(email))
        if ttl and ttl > 0:
            return ThrottleState(limited=True, retry_after=ttl)
        return ThrottleState(limited=False)
    except redis.RedisError as exc:
        return _unavailable(exc)


def record_failure(email: str) -> ThrottleState:
    """
    Count one failed attempt, locking the account if it crosses the threshold.
    """
    try:
        pipe = redis_client.pipeline()
        pipe.incr(_fail_key(email))
        pipe.expire(_fail_key(email), settings.login_window_seconds)
        attempts = pipe.execute()[0]

        if attempts < settings.login_max_attempts:
            return ThrottleState(limited=False)

        # Escalate: each lockout for this account is twice the previous one.
        lockouts = redis_client.incr(_escalation_key(email))
        redis_client.expire(_escalation_key(email), _ESCALATION_TTL)
        retry_after = min(
            settings.login_lockout_seconds * (2 ** (lockouts - 1)),
            _ESCALATION_TTL,
        )

        pipe = redis_client.pipeline()
        pipe.setex(_lock_key(email), retry_after, "1")
        pipe.delete(_fail_key(email))
        pipe.execute()

        log.warning(
            "login locked for %s after %s attempts (%ss)",
            email,
            attempts,
            retry_after,
        )
        return ThrottleState(limited=True, retry_after=retry_after)
    except redis.RedisError as exc:
        return _unavailable(exc)


def reset(email: str) -> None:
    """Clear the failure counter after a successful login."""
    try:
        redis_client.delete(_fail_key(email))
    except redis.RedisError as exc:
        log.warning("could not reset login throttle for %s: %s", email, exc)
