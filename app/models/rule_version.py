"""Rule version registry.

The classification rule set is fixed and versioned (CLAUDE.md §1). Every case
records which rule version produced its Part A/B/C/D classification, so a filing
can always be traced back to the exact rules in force when it was decided.

This table is global (not firm-scoped): the rule set is the same for every firm.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class RuleVersion(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "rule_versions"

    # e.g. "2024.1" — matches settings.active_rule_version and the version
    # string baked into the rules engine module.
    version: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
