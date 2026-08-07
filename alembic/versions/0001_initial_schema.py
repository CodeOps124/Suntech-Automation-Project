"""initial schema — firms, users, clients, vendors, cases, documents, events, rules

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-20
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # gen_random_uuid() lives in pgcrypto.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "firms",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("plan_tier", sa.String(32), nullable=False, server_default="ca_starter"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "rule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("version", sa.String(32), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "firm_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="analyst"),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_firm_users_firm_id", "firm_users", ["firm_id"])

    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("pan", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_clients_firm_id", "clients", ["firm_id"])

    op.create_table(
        "vendors",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("tin", sa.String(64), nullable=True),
        sa.Column("trc_valid_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_vendors_firm_id", "vendors", ["firm_id"])
    op.create_index("ix_vendors_client_id", "vendors", ["client_id"])

    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="intake"),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("purpose_code", sa.String(16), nullable=True),
        sa.Column("part_classification", sa.String(1), nullable=True),
        sa.Column("rule_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rule_versions.id"), nullable=True),
        sa.Column("classification_reasons", postgresql.JSONB(), nullable=True),
        sa.Column("dsc_reference", sa.String(255), nullable=True),
        sa.Column("udin", sa.String(64), nullable=True),
        sa.Column("certified_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firm_users.id"), nullable=True),
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_cases_firm_id", "cases", ["firm_id"])
    op.create_index("ix_cases_client_id", "cases", ["client_id"])
    op.create_index("ix_cases_vendor_id", "cases", ["vendor_id"])
    op.create_index("ix_cases_status", "cases", ["status"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=True),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("extracted_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_documents_firm_id", "documents", ["firm_id"])
    op.create_index("ix_documents_case_id", "documents", ["case_id"])

    op.create_table(
        "case_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firm_users.id"), nullable=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("old_status", sa.String(32), nullable=True),
        sa.Column("new_status", sa.String(32), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_case_events_firm_id", "case_events", ["firm_id"])
    op.create_index("ix_case_events_case_id", "case_events", ["case_id"])


def downgrade() -> None:
    for table in (
        "case_events",
        "documents",
        "cases",
        "vendors",
        "clients",
        "firm_users",
        "rule_versions",
        "firms",
    ):
        op.drop_table(table)
