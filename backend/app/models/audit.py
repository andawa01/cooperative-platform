"""
AuditLog — append-only record of who changed money-relevant state.

Why a table and not a log line (D-031): a log line is a debugging aid; this
is evidence. Someone must one day answer "who reversed this payment, when,
and what did it look like before?" — and the answer must not depend on
retention settings of a log shipper.

Properties this design commits to:

- **Same transaction as the change.** An audit row is inserted by the same
  session, inside the same `write_transaction` as the mutation it describes.
  Either both exist or neither does. A failed action never leaves an audit
  row claiming it happened, and a successful action can never be missing one.
- **Append-only, enforced by the database.** A BEFORE UPDATE OR DELETE
  trigger raises. "We never modify audit rows" as a policy is a comment;
  as a trigger it is a fact. (The seed can still TRUNCATE — that is a
  deliberate admin action, not a mutation of history.)
- **No foreign keys to the audited entity.** `entity_id` is a plain UUID.
  The audit must outlive whatever it describes; a cascade or a restore
  must not be able to delete the evidence of a change.
- **Actor is a soft reference.** `actor_id` points at `users.id` with
  ON DELETE SET NULL: if an account ever disappears, the entry survives and
  reports a missing actor rather than being blocked or cascaded away.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel

# The wire set (D-031). Kept as data rather than a DB constraint: adding a
# new action is a release, not a migration. A CHECK would turn a missed
# migration step into a production insert failure.
AUDIT_ACTIONS = (
    "delivery.create",
    "delivery.value",
    "delivery.reverse",
    "payment.create",
    "payment.reverse",
    "rate.create",
    "farmer.create",
    "farmer.update",
    "farmer.verify",
    "farmer.archive",
    "user.create",
    "user.password_change",
)

# Entity types an action can describe. Display-only as well.
AUDIT_ENTITY_TYPES = (
    "delivery",
    "payment",
    "rate",
    "farmer",
    "user",
)


class AuditLog(BaseModel):
    __tablename__ = "audit_log"

    # None means the system itself (bootstrap registration, before any user
    # exists to act).
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Dotted verb: "<entity>.<action>". Filterable and readable.
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Snapshots of the fields that matter — not the whole row, and never
    # secrets (no password hashes, no phone-less PII dumps). `before` is
    # None for creations; `after` is None when the entity was removed from
    # view (nothing is removed in MVP).
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Ties the entry to the request id in the log stream (D-029), so an
    # auditor can jump from an entry to the exact request line.
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_created", "created_at"),
        Index("ix_audit_log_action_created", "action", "created_at"),
        CheckConstraint(
            "action IN (" + ", ".join(f"'{a}'" for a in AUDIT_ACTIONS) + ")",
            name="ck_audit_log_action_valid",
        ),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity_type}:{self.entity_id}>"
