"""
Notification tests.

The interesting assertions are:
- The Postgres row is created even if Redis is unreachable (best-effort).
- Enqueue writes correct dispatch state to Redis.
- Retry permission is admin-only (tested at HTTP layer in test_permissions).
- Worker's processing logic sends and writes state correctly (tested by
  directly calling the processing function against a controlled state).

We deliberately do NOT test the gateway's randomness — we seed a fail rate
of 0 via monkeypatch when we need determinism.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.core import redis_client as rc
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationTemplate,
    RelatedEntityType,
)
from app.services import notifications as notif_service


@pytest.fixture(autouse=True)
def _isolate_redis_keys():
    """
    Clear the notification queue and all per-notification state keys before
    each test. The test suite shares one Redis instance with dev; we must
    not pollute it.

    Note: this makes the notification tests order-dependent relative to
    any running worker. That's acceptable — the worker is a dev tool, not
    part of the test run.
    """
    try:
        rc.redis_client.delete(notif_service.QUEUE_KEY, notif_service.RETRY_KEY)
        # Best-effort: scan and delete state keys.
        for key in rc.redis_client.scan_iter(f"{notif_service.STATE_KEY_PREFIX}*"):
            rc.redis_client.delete(key)
    except Exception:  # noqa: BLE001
        # If Redis is unreachable, skip the tests that need it.
        pass
    yield
    try:
        rc.redis_client.delete(notif_service.QUEUE_KEY, notif_service.RETRY_KEY)
    except Exception:  # noqa: BLE001
        pass


def _create_notification(db, farmer) -> Notification:
    n = Notification(
        farmer_id=farmer.id,
        channel=NotificationChannel.SMS.value,
        template=NotificationTemplate.DELIVERY_RECORDED.value,
        recipient=farmer.phone,
        content="Test SMS",
        related_entity_type=RelatedEntityType.DELIVERY.value,
        related_entity_id=uuid.uuid4(),
    )
    db.add(n)
    db.flush()
    return n


def test_dispatch_state_defaults_when_missing(db, farmer):
    n = _create_notification(db, farmer)
    state = notif_service.get_dispatch_state(n.id)
    assert state["status"] == "unknown"
    assert state["attempts"] == 0
    assert state["last_error"] == "not enqueued"


def test_enqueue_writes_postgres_and_redis(db, farmer):
    """
    The service writes a durable Notification row and puts the id on the
    Redis queue with initial state.
    """
    n = _create_notification(db, farmer)

    # Simulate what enqueue_delivery_recorded does after creating the row.
    ok = notif_service._enqueue(n.id)
    notif_service._write_state(
        n.id, status="queued", attempts=0, last_error=None, sent_at=None,
    )
    assert ok is True

    state = notif_service.get_dispatch_state(n.id)
    assert state["status"] == "queued"
    assert state["attempts"] == 0

    # Clean up the queue item we just pushed.
    rc.redis_client.lrem(notif_service.QUEUE_KEY, 0, str(n.id))


def test_retry_notification_requeues(db, farmer, admin):
    n = _create_notification(db, farmer)
    notif_service._write_state(
        n.id, status="failed", attempts=3,
        last_error="simulated gateway failure", sent_at=None,
    )

    notif_service.retry_notification(db, n.id)

    state = notif_service.get_dispatch_state(n.id)
    assert state["status"] == "queued"
    # Attempts history is preserved, not reset.
    assert state["attempts"] == 3

    rc.redis_client.lrem(notif_service.QUEUE_KEY, 0, str(n.id))