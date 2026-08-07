"""restricted application role — RLS actually enforced for the app

Revision ID: 0003_app_role
Revises: 0002_rls_and_audit_guard
Create Date: 2026-07-21

The compose Postgres user is the DB owner (a superuser in dev), and superusers
bypass RLS entirely — verified live: a bogus X-Firm-ID could read every firm's
cases. This migration creates a NON-superuser `app_user` role for the normal
app path so the 0002 policies actually bite.

Dev password is hardcoded for the local stack. In production, change it
immediately (ALTER ROLE app_user WITH PASSWORD ...) or manage the role
out-of-band; the DO block below skips creation if the role already exists.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_app_role"
down_revision: str | None = "0002_rls_and_audit_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
                CREATE ROLE app_user WITH LOGIN PASSWORD 'app_user_dev_pw'
                    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            END IF;
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO app_user")
    # CRUD on current tables. case_events UPDATE/DELETE is still blocked by the
    # append-only trigger regardless of grants.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
    # And on tables future migrations create (as the owner role).
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user"
    )


def downgrade() -> None:
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM app_user")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_user")
    op.execute("REVOKE USAGE ON SCHEMA public FROM app_user")
    # Role is left in place — other databases may share it.
