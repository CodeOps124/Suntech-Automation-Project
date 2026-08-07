"""Case, document, and case-event models.

One case = one remittance (CLAUDE.md §10). The current state lives on the
`cases` row; the full history lives ONLY in `case_events`, which is
append-only and must never be overwritten.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import CaseStatus
from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Case(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "cases"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=CaseStatus.INTAKE.value, index=True
    )

    # Remittance details (populated by OCR/extraction, confirmed by validation).
    # remittance_date anchors the financial-year threshold window; when absent,
    # created_at is the fallback anchor (see services/classification.py).
    remittance_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)  # ISO 4217
    purpose_code: Mapped[str | None] = mapped_column(String(16), nullable=True)  # RBI purpose code

    # Classification output (set by the deterministic rules engine only).
    part_classification: Mapped[str | None] = mapped_column(String(1), nullable=True)
    rule_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_versions.id"), nullable=True
    )
    # Structured reason codes / evidence from classification (§7.1 step 5:
    # "must retain reason codes and evidence").
    classification_reasons: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Human certification artefacts — entered by a CA in the review dashboard,
    # NEVER by automation (§1). Presence of these implies status == certified.
    dsc_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    udin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    certified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm_users.id"), nullable=True
    )
    certified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    client: Mapped["Client"] = relationship(back_populates="cases")  # noqa: F821
    vendor: Mapped["Vendor"] = relationship(back_populates="cases")  # noqa: F821
    documents: Mapped[list["Document"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    events: Mapped[list["CaseEvent"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseEvent.created_at"
    )


class Document(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "documents"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)  # S3 key
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Extraction confidence from the OCR step; low confidence -> human review.
    confidence_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    case: Mapped["Case"] = relationship(back_populates="documents")


class CaseEvent(Base, UUIDPKMixin, TimestampMixin):
    """Append-only audit trail. Never UPDATE or DELETE a row here (§10).

    A DB trigger (see migration) blocks UPDATE/DELETE as a hard guarantee, so
    the audit log cannot be tampered with even by a buggy code path.
    """

    __tablename__ = "case_events"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firm_users.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Free-form detail for the human-readable activity feed (§15).
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship(back_populates="events")
