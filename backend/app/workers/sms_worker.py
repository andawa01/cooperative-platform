"""
SMS dispatch worker.

Runs as a SEPARATE process from the API:

    python -m app.workers.sms_worker

The worker loop:
1. Move any items from the retry sorted set whose score <= now onto the
   immediate queue (this is our backoff mechanism).
2. BRPOP from the immediate queue (blocking pop, 5-second timeout).
3. If a job is ready, process it:
   a. Load the durable Notification record from Postgres.
   b. Mark Redis state as 'sending', increment attempts.
   c. Call the simulated gateway.
   d. On success: mark 'sent'.
      On failure: if attempts < max, schedule a retry with backoff.
                  Otherwise, mark 'failed'.

Semantics: at-least-once. A crash after the gateway returns success but
before we write 'sent' means the SMS might be sent again on retry. For
SMS notifications this is acceptable. Documented in D-024.

Shutdown: SIGINT/SIGTERM sets a flag; the loop exits after the current
job (if any) finishes. This gives us a clean Ctrl+C without losing work.
"""
import logging
import signal
import sys
import time
from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session

import redis

from app.core.config import settings
from app.core.redis_client import redis_client
from app.db.session import SessionLocal
from app.models.notification import Notification
from app.services import sms_gateway
from app.services import notifications as notif_service


log = logging.getLogger("shambatrack.worker")


# Loop control.
_stop = False


def _handle_signal(signum, frame):  # noqa: ARG001
    global _stop
    log.info("received signal %s, shutting down after current job", signum)
    _stop = True


def _promote_due_retries() -> int:
    """
    Move any retry items whose score is now in the past to the main queue.
    Returns the number moved (for logging / testing).
    """
    now = datetime.now(timezone.utc).timestamp()
    try:
        due = redis_client.zrangebyscore(
            notif_service.RETRY_KEY, "-inf", now, start=0, num=50
        )
    except redis.RedisError as exc:
        log.error("retry sweep failed: %s", exc)
        return 0

    moved = 0
    for notification_id in due:
        try:
            # Best-effort atomic move: remove from sorted set, push to list.
            # If we crash between, the item is lost from the queue but the
            # Postgres row is intact and admins can retry via the API.
            removed = redis_client.zrem(notif_service.RETRY_KEY, notification_id)
            if removed:
                redis_client.lpush(notif_service.QUEUE_KEY, notification_id)
                moved += 1
        except redis.RedisError as exc:
            log.error("failed to promote %s: %s", notification_id, exc)
    return moved


def _process(notification_id: str) -> None:
    """
    Process one notification: load the durable record, call the gateway,
    update the Redis state.
    """
    db: Session = SessionLocal()
    try:
        try:
            nid = uuid.UUID(notification_id)
        except (ValueError, TypeError):
            log.error("invalid notification id in queue: %r", notification_id)
            return

        notification = db.get(Notification, nid)
        if notification is None:
            log.warning("notification %s not in DB, dropping", nid)
            return

        state = notif_service.get_dispatch_state(nid)
        if state["status"] == "sent":
            log.info("notification %s already sent, skipping", nid)
            return

        attempts = state["attempts"] + 1

        # Mark as sending before the gateway call. If we crash here, admins
        # see 'sending' and can retry. This is the at-least-once trade.
        notif_service._write_state(
            nid, status="sending", attempts=attempts,
            last_error=None, sent_at=None,
        )

        result = sms_gateway.send(notification.recipient, notification.content)

        if result.success:
            notif_service._write_state(
                nid,
                status="sent",
                attempts=attempts,
                last_error=None,
                sent_at=datetime.now(timezone.utc),
            )
            log.info("sent notification %s to %s", nid, notification.recipient)
            return

        # Failure path.
        if attempts >= settings.sms_max_attempts:
            notif_service._write_state(
                nid,
                status="failed",
                attempts=attempts,
                last_error=result.error,
                sent_at=None,
            )
            log.warning(
                "notification %s permanently failed after %d attempts: %s",
                nid, attempts, result.error,
            )
            return

        # Schedule a retry with backoff. backoff_seconds is indexed by
        # (attempts - 1). If we somehow exceed the tuple length, use the
        # last value.
        idx = min(attempts - 1, len(settings.sms_backoff_seconds) - 1)
        delay = settings.sms_backoff_seconds[idx]
        notif_service._write_state(
            nid,
            status="queued",
            attempts=attempts,
            last_error=result.error,
            sent_at=None,
        )
        notif_service._enqueue(nid, delay_seconds=delay)
        log.info(
            "notification %s failed (attempt %d), retrying in %ds",
            nid, attempts, delay,
        )
    finally:
        db.close()


def run_loop() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    log.info("worker started; queue=%s retry=%s",
             notif_service.QUEUE_KEY, notif_service.RETRY_KEY)

    while not _stop:
        # 1. Promote due retries.
        moved = _promote_due_retries()
        if moved:
            log.info("promoted %d retries", moved)

        # 2. Block on the queue with a short timeout so we can also promote
        #    retries on a schedule.
        try:
            item = redis_client.brpop(notif_service.QUEUE_KEY, timeout=5)
        except redis.RedisError as exc:
            log.error("BRPOP failed: %s; sleeping", exc)
            time.sleep(5)
            continue

        if item is None:
            continue

        # BRPOP returns (key, value). We only need the value.
        _key, notification_id = item
        try:
            _process(notification_id)
        except Exception as exc:  # noqa: BLE001
            # A single bad job must not take down the worker.
            log.exception("unhandled error processing %s: %s",
                          notification_id, exc)

    log.info("worker stopped")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())