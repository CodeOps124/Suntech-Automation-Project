"""row-level security policies + append-only guard on case_events

Revision ID: 0002_rls_and_audit_guard
Revises: 0001_initial_schema
Create Date: 2026-07-20

Multi-tenancy is enforced HERE, in the database (CLAUDE.md §1). Every
firm-scoped table gets RLS enabled and a policy that only exposes rows whose
firm_id equals the session GUC ``app.current_firm_id`` (set by
app.db.session.tenant_session). App-layer filtering is not relied upon.

`firms` itself is intentionally NOT firm-scoped (it defines the firms).

case_events also gets a trigger that blocks UPDATE and DELETE, so the audit
trail is append-only as a hard database guarantee, not merely by convention.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_rls_and_audit_guard"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table that carries firm_id and must be tenant-isolated.
FIRM_SCOPED_TABLES = (
    "firm_users",
    "clients",
    "vendors",
    "cases",
    "documents",
    "case_events",
)


def upgrade() -> None:
    # ---- Row-level security -------------------------------------------------
    for table in FIRM_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE so even the table owner is subject to the policy (owners bypass
        # RLS by default). The seed path uses a BYPASSRLS role instead.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_firm_isolation ON {table}
            USING (firm_id = current_setting('app.current_firm_id', true)::uuid)
            WITH CHECK (firm_id = current_setting('app.current_firm_id', true)::uuid)
            """
        )

    # ---- Append-only guard on case_events -----------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION case_events_block_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'case_events is append-only: % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_case_events_append_only
        BEFORE UPDATE OR DELETE ON case_events
        FOR EACH ROW EXECUTE FUNCTION case_events_block_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_case_events_append_only ON case_events")
    op.execute("DROP FUNCTION IF EXISTS case_events_block_mutation()")
    for table in FIRM_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_firm_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
