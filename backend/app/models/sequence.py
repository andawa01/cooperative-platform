"""
Document sequences — human-readable numbers a person can quote.

A UUID is fine in a URL and useless over the phone. Farmers quote slip numbers,
so documents that get printed or read out loud carry a short sequential handle
(`D-2026-000123`) alongside their id.

One counter row per document family and calendar year. The row is locked while
a number is handed out, which serializes the allocation; because the number is
taken inside the same transaction as the document itself, a failed write rolls
the counter back and the sequence stays gapless. See D-034.
"""

from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class DocumentSequence(BaseModel):
    __tablename__ = "document_sequences"

    # Document family, e.g. "delivery_receipt".
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    # Calendar year the counter belongs to; sequences restart each January.
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    # Highest number issued so far in this (name, year).
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("name", "year", name="uq_document_sequence_scope"),
        CheckConstraint("last_value >= 0", name="ck_document_sequence_non_negative"),
    )
