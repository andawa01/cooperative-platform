"""
Tests for the SMS worker and notification dispatch path.

Covers:
- _process: gateway success, failure → retry, max attempts → failed,
  already-sent skip, invalid id, notification not in DB.
- _promote_due_retries: due (past timestamp), not due (future timestamp).
- Notification service: payment enqueue, retry via API.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.redis_client import redis_client
from app.models.notification import NotificationChannel, NotificationTemplate
from app.models.payment import PaymentMethod
from app.schemas.delivery import DeliveryCreate
from app.schemas.payment import PaymentCreate
from app.services import delivery as delivery_service
from app.services import notifications as notif_service
from app.services import payment as payment_service
from app.services.sms_gateway import GatewayResult
from app.workers import sms_worker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_redis():
    """Clear notification Redis keys before and after each test to prevent
    cross-test contamination. The suite shares one Redis instance with dev."""
    try:
        redis_client.delete(notif_service.QUEUE_KEY, notif_service.RETRY_KEY)
        for key in redis_client.scan_iter(f"{notif_service.STATE_KEY_PREFIX}*"):
            redis_client.delete(key)
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        redis_client.delete(notif_service.QUEUE_KEY, notif_service.RETRY_KEY)
        for key in redis_client.scan_iter(f"{notif_service.STATE_KEY_PREFIX}*"):
            redis_client.delete(key)
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def worker_session(db, monkeypatch):
    """Patch sms_worker.SessionLocal so _process reads from the test DB.

    The worker normally opens its own session on the production engine.
    We redirect it to a session sharing the test connection so it can see
    rows seeded by the db fixture (which live in an uncommitted savepoint
    transaction).
    """
    bind = db.get_bind()
    factory = sessionmaker(
        bind=bind,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(sms_worker, "SessionLocal", factory)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_delivery_notification(db, farmer, produce_line, clerk):
    """Record a delivery and enqueue its notification. Returns the Notification."""
    delivery = delivery_service.record_delivery(
        db,
        DeliveryCreate(
            farmer_id=farmer.id,
            produce_line_id=produce_line.id,
            quantity=Decimal("10.0000"),
            delivered_at=datetime.now(UTC),
        ),
        actor=clerk,
    )
    return notif_service.enqueue_delivery_recorded(db, delivery)


def _pop_from_queue(notification_id):
    """Simulate BRPOP delivering a job to _process (removes from the queue)."""
    redis_client.lrem(notif_service.QUEUE_KEY, 0, str(notification_id))


# ---------------------------------------------------------------------------
# 1. Gateway success path
# ---------------------------------------------------------------------------


def test_process_gateway_success(db, worker_session, farmer, produce_line, clerk):
    """Gateway returns success → dispatch state becomes 'sent' with attempts=1."""
    n = _seed_delivery_notification(db, farmer, produce_line, clerk)
    _pop_from_queue(n.id)

    with patch(
        "app.services.sms_gateway.send",
        return_value=GatewayResult(
            success=True, provider_message_id="sim-001", error=None
        ),
    ):
        sms_worker._process(str(n.id))

    state = notif_service.get_dispatch_state(n.id)
    assert state["status"] == "sent"
    assert state["attempts"] == 1


# ---------------------------------------------------------------------------
# 2. Gateway failure → retry
# ---------------------------------------------------------------------------


def test_process_gateway_failure_retries(
    db, worker_session, farmer, produce_line, clerk
):
    """Gateway returns failure → state becomes 'queued' with attempts=1 and the
    notification lands on the retry sorted set (not the immediate queue)."""
    n = _seed_delivery_notification(db, farmer, produce_line, clerk)
    _pop_from_queue(n.id)

    with patch(
        "app.services.sms_gateway.send",
        return_value=GatewayResult(
            success=False, provider_message_id=None, error="simulated gateway failure"
        ),
    ):
        sms_worker._process(str(n.id))

    state = notif_service.get_dispatch_state(n.id)
    assert state["status"] == "queued"
    assert state["attempts"] == 1

    # On the retry sorted set, not the immediate queue.
    assert redis_client.zscore(notif_service.RETRY_KEY, str(n.id)) is not None
    queue_items = redis_client.lrange(notif_service.QUEUE_KEY, 0, -1)
    assert str(n.id) not in queue_items


# ---------------------------------------------------------------------------
# 3. Max attempts → permanently failed
# ---------------------------------------------------------------------------


def test_process_max_attempts_failed(
    db, worker_session, monkeypatch, farmer, produce_line, clerk
):
    """With sms_max_attempts=1, a single gateway failure marks the notification
    as 'failed'."""
    monkeypatch.setattr(settings, "sms_max_attempts", 1)

    n = _seed_delivery_notification(db, farmer, produce_line, clerk)
    _pop_from_queue(n.id)

    with patch(
        "app.services.sms_gateway.send",
        return_value=GatewayResult(
            success=False, provider_message_id=None, error="simulated gateway failure"
        ),
    ):
        sms_worker._process(str(n.id))

    state = notif_service.get_dispatch_state(n.id)
    assert state["status"] == "failed"
    assert state["attempts"] == 1


# ---------------------------------------------------------------------------
# 4. Retry promotion (past timestamp)
# ---------------------------------------------------------------------------


def test_promote_due_retries_past():
    """An item in the retry sorted set with a past timestamp is moved to the
    immediate queue."""
    nid = str(uuid.uuid4())
    now = datetime.now(UTC).timestamp()
    redis_client.zadd(notif_service.RETRY_KEY, {nid: now - 10})

    moved = sms_worker._promote_due_retries()

    assert moved == 1
    queue_items = redis_client.lrange(notif_service.QUEUE_KEY, 0, -1)
    assert nid in queue_items
    assert redis_client.zscore(notif_service.RETRY_KEY, nid) is None


# ---------------------------------------------------------------------------
# 5. Retry promotion (future timestamp)
# ---------------------------------------------------------------------------


def test_promote_due_retries_future():
    """An item with a future timestamp stays on the retry sorted set."""
    nid = str(uuid.uuid4())
    now = datetime.now(UTC).timestamp()
    redis_client.zadd(notif_service.RETRY_KEY, {nid: now + 3600})

    moved = sms_worker._promote_due_retries()

    assert moved == 0
    assert redis_client.zscore(notif_service.RETRY_KEY, nid) is not None
    queue_items = redis_client.lrange(notif_service.QUEUE_KEY, 0, -1)
    assert nid not in queue_items


# ---------------------------------------------------------------------------
# 6. Already-sent skip
# ---------------------------------------------------------------------------


def test_process_already_sent_skip(
    db, worker_session, farmer, produce_line, clerk
):
    """A notification already marked 'sent' is skipped — the gateway is not
    called again."""
    n = _seed_delivery_notification(db, farmer, produce_line, clerk)
    _pop_from_queue(n.id)

    notif_service._write_state(
        n.id,
        status="sent",
        attempts=1,
        last_error=None,
        sent_at=datetime.now(UTC),
    )

    with patch("app.services.sms_gateway.send") as mock_send:
        sms_worker._process(str(n.id))
        mock_send.assert_not_called()

    state = notif_service.get_dispatch_state(n.id)
    assert state["status"] == "sent"
    assert state["attempts"] == 1


# ---------------------------------------------------------------------------
# 7. Invalid notification id
# ---------------------------------------------------------------------------


def test_process_invalid_id(db, worker_session):
    """An invalid (non-UUID) notification id is logged and skipped without
    crashing."""
    # Should not raise.
    sms_worker._process("not-a-uuid")


# ---------------------------------------------------------------------------
# 8. Notification not in DB
# ---------------------------------------------------------------------------


def test_process_not_in_db(db, worker_session):
    """A valid UUID that doesn't exist in the DB is skipped without crashing."""
    # Should not raise.
    sms_worker._process(str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# 9. Payment notification enqueue
# ---------------------------------------------------------------------------


def test_enqueue_payment_recorded(db, farmer, admin):
    """enqueue_payment_recorded creates a Notification row with
    template='payment_recorded'."""
    payment, _ = payment_service.record_payment(
        db,
        PaymentCreate(
            farmer_id=farmer.id,
            amount=Decimal("100.00"),
            currency="KES",
            method=PaymentMethod.CASH,
            paid_at=datetime.now(UTC),
            idempotency_key="test-payment-key-001",
        ),
        actor=admin,
    )

    n = notif_service.enqueue_payment_recorded(db, payment)

    assert n is not None
    assert n.template == NotificationTemplate.PAYMENT_RECORDED.value
    assert n.template == "payment_recorded"
    assert n.channel == NotificationChannel.SMS.value
    assert n.recipient == farmer.phone


# ---------------------------------------------------------------------------
# 10. Retry via API service
# ---------------------------------------------------------------------------


def test_retry_notification(db, farmer, produce_line, clerk):
    """retry_notification re-enqueues a failed notification with status='queued'."""
    n = _seed_delivery_notification(db, farmer, produce_line, clerk)
    _pop_from_queue(n.id)

    # Simulate a permanently failed dispatch.
    notif_service._write_state(
        n.id,
        status="failed",
        attempts=3,
        last_error="simulated gateway failure",
        sent_at=None,
    )

    notif_service.retry_notification(db, n.id)

    state = notif_service.get_dispatch_state(n.id)
    assert state["status"] == "queued"
    queue_items = redis_client.lrange(notif_service.QUEUE_KEY, 0, -1)
    assert str(n.id) in queue_items
