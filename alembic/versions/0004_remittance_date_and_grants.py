"""remittance_date column + tighten app_user grants

Revision ID: 0004_remittance_date_and_grants
Revises: 0003_app_role
Create Date: 2026-07-21

Two fixes from external code review (Codex):
  * cases.remittance_date — anchors the FY threshold window to the case's own
    date instead of wall-clock classification time (a March remittance
    classified in April must stay in the old FY).
  * app_user loses INSERT/UPDATE/DELETE on the two tables that are NOT
    RLS-protected (firms, rule_versions). The app path only ever reads them;
    writes go through the privileged role.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_remittance_date_and_grants"
down_revision: str | None = "0003_app_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("remittance_date", sa.Date(), nullable=True))
    op.execute("REVOKE INSERT, UPDATE, DELETE ON firms FROM app_user")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON rule_versions FROM app_user")


def downgrade() -> None:
    op.execute("GRANT INSERT, UPDATE, DELETE ON firms TO app_user")
    op.execute("GRANT INSERT, UPDATE, DELETE ON rule_versions TO app_user")
    op.drop_column("cases", "remittance_date")
