"""Client and vendor models.

`clients` are the CA firm's own client companies (the remitters).
`vendors` are the foreign payees, scoped to a client — needed for the
per-vendor per-FY aggregate threshold check in the rules engine.

Both carry firm_id directly (denormalised from client for vendors) so a single
RLS policy shape protects every case-related table uniformly.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Client(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "clients"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)  # Indian PAN

    firm: Mapped["Firm"] = relationship(back_populates="clients")  # noqa: F821
    vendors: Mapped[list["Vendor"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    cases: Mapped[list["Case"]] = relationship(  # noqa: F821
        back_populates="client", cascade="all, delete-orphan"
    )


class Vendor(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "vendors"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tin: Mapped[str | None] = mapped_column(String(64), nullable=True)  # foreign tax id
    trc_valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)  # tax residency cert

    client: Mapped["Client"] = relationship(back_populates="vendors")
    cases: Mapped[list["Case"]] = relationship(back_populates="vendor")  # noqa: F821
