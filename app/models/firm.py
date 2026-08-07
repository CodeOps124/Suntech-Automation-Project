"""Firm and firm-user models — the tenant boundary.

A CA firm is the tenant (CLAUDE.md §1). `firms` is the ONLY case-related table
not scoped by firm_id (it defines the firms themselves). Everything else carries
firm_id and is protected by RLS.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import PlanTier, UserRole
from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Firm(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "firms"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Stored as the enum *value* (e.g. "ca_starter"); the platform never sells
    # anything outside PLAN_CATALOG.
    plan_tier: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PlanTier.CA_STARTER.value
    )

    users: Mapped[list["FirmUser"]] = relationship(back_populates="firm", cascade="all, delete-orphan")
    clients: Mapped[list["Client"]] = relationship(back_populates="firm", cascade="all, delete-orphan")  # noqa: F821


class FirmUser(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "firm_users"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("firms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=UserRole.ANALYST.value)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    firm: Mapped["Firm"] = relationship(back_populates="users")
