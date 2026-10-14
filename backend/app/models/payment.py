"""
Payment and PaymentAllocation — the debit side of the ledger.

See DECISIONS.md D-010 for the full reasoning. Key points:

- A Payment records money that moved TO a farmer.
- A PaymentAllocation records which deliveries that money settled.
- Both use the same-table reversal pattern as Delivery:
    normal:   positive amount, reversal_of_id IS NULL
    reversal: negative amount, reversal_of_id points at the original
- Amounts are Numeric(12, 4) — never float.
- Idempotency keys make retried payment requests safe.
- Balances are NEVER stored. They are derived from SUM(payments) and
  SUM(allocations).
- Concurrency is enforced by a farmer-row lock, not by the DB (see D-010).
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    MOBILE_MONEY = "mobile_money"
    BANK_TRANSFER = "bank_transfer"


class PaymentStatus(str, enum.Enum):
    """
    Deliberately minimal for MVP. We are not integrating a real payment
    gateway (out of scope per the brief), so 'pending' and 'failed' states
    would be theatre. When we simulate a gateway later, we can add states
    without a migration pain — the column is a VARCHAR with a CHECK.
    """
    CONFIRMED = "confirmed"
    REVERSED = "reversed"


PAYMENT_METHOD_VALUES = tuple(m.value for m in PaymentMethod)
PAYMENT_STATUS_VALUES = tuple(s.value for s in PaymentStatus)


class Payment(BaseModel):
    __tablename__ = "payments"

    # --- Who and how much -----------------------------------------------
    farmer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farmers.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # --- How and when ---------------------------------------------------
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    # External reference (M-Pesa code, bank ref, cash voucher number).
    # Nullable because cash payments may have no reference.
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # --- Idempotency ----------------------------------------------------
    # Client-generated UUID per payment intent. Prevents the "clicked pay
    # twice because the network dropped" double-payment.
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # SHA-256 hex of the canonical request body. Used together with
    # idempotency_key to distinguish:
    #   (same key, same fingerprint) → replay, return existing payment
    #   (same key, different fingerprint) → 409, client reused the key
    idempotency_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    # --- Status and reversal --------------------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PaymentStatus.CONFIRMED.value,
        server_default=PaymentStatus.CONFIRMED.value,
    )
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), nullable=True
    )

    # --- Context --------------------------------------------------------
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Constraints ----------------------------------------------------
    __table_args__ = (
        # Idempotency: one payment per intent key, globally.
        UniqueConstraint("idempotency_key", name="uq_payment_idempotency_key"),

        # Normal vs reversal shape (same "both sides must agree" trick).
        CheckConstraint(
            "(amount > 0 AND reversal_of_id IS NULL) OR "
            "(amount < 0 AND reversal_of_id IS NOT NULL)",
            name="ck_payment_normal_or_reversal",
        ),

        CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id <> id",
            name="ck_payment_no_self_reversal",
        ),

        # No double-reversal of the same payment.
        UniqueConstraint("reversal_of_id", name="uq_payment_reversal_of"),

        # ISO 4217 currency.
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_payment_currency_iso4217",
        ),

        # Method must be one of a known set.
        CheckConstraint(
            "method IN (" + ", ".join(f"'{v}'" for v in PAYMENT_METHOD_VALUES) + ")",
            name="ck_payment_method_valid",
        ),

        # Status must be one of a known set.
        CheckConstraint(
            "status IN (" + ", ".join(f"'{v}'" for v in PAYMENT_STATUS_VALUES) + ")",
            name="ck_payment_status_valid",
        ),

        # Physical payment cannot be recorded AFTER the fact by more than
        # 1 hour (clock skew tolerance). Backdating is fine.
        CheckConstraint(
            "paid_at <= recorded_at + interval '1 hour'",
            name="ck_payment_paid_at_not_future",
        ),

        Index("ix_payment_farmer_paid_at", "farmer_id", "paid_at"),
    )

    # --- Derived helpers ------------------------------------------------
    @property
    def is_reversal(self) -> bool:
        return self.reversal_of_id is not None

    def __repr__(self) -> str:
        kind = "REV" if self.is_reversal else "PAY"
        return (
            f"<Payment {kind} {self.amount} {self.currency} "
            f"farmer={self.farmer_id} at={self.paid_at}>"
        )


class PaymentAllocation(BaseModel):
    """
    Records that a payment settled a portion (or all) of a delivery.

    Same reversal pattern as Payment and Delivery:
      normal:   positive amount, reversal_of_id IS NULL
      reversal: negative amount, reversal_of_id points at the original
    """
    __tablename__ = "payment_allocations"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deliveries.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_allocations.id", ondelete="RESTRICT"), nullable=True
    )

    __table_args__ = (
        # Normal vs reversal shape.
        CheckConstraint(
            "(amount > 0 AND reversal_of_id IS NULL) OR "
            "(amount < 0 AND reversal_of_id IS NOT NULL)",
            name="ck_allocation_normal_or_reversal",
        ),

        CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id <> id",
            name="ck_allocation_no_self_reversal",
        ),

        # No double-reversal of the same allocation.
        UniqueConstraint("reversal_of_id", name="uq_allocation_reversal_of"),

        # One normal allocation per (payment, delivery) pair. Two payments
        # may each allocate against the same delivery (partial payments).
        # The partial unique index below handles the "normal only" case.
        Index(
            "uq_allocation_payment_delivery_normal",
            "payment_id",
            "delivery_id",
            unique=True,
            postgresql_where="reversal_of_id IS NULL",
        ),

        Index("ix_allocation_delivery", "delivery_id"),
        Index("ix_allocation_payment", "payment_id"),
    )

    @property
    def is_reversal(self) -> bool:
        return self.reversal_of_id is not None

    def __repr__(self) -> str:
        kind = "REV" if self.is_reversal else "ALC"
        return (
            f"<PaymentAllocation {kind} {self.amount} "
            f"payment={self.payment_id} delivery={self.delivery_id}>"
        )