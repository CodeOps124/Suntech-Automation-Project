"""Database engine, session factory, and tenant-scoped session helpers.

Multi-tenancy (CLAUDE.md §1 non-negotiable) is enforced at the Postgres level
with row-level security, NOT just application filtering. Every RLS policy reads
the session GUC ``app.current_firm_id``. The helpers here are the only
sanctioned way to set it, so tenant scoping cannot be forgotten at a call site.

Two access modes:
  * ``tenant_session(firm_id)``   — normal app path. RLS active, scoped to one firm.
  * ``privileged_session()``      — bootstrap/admin only (create a firm, run seeds).
                                    Uses a role that bypasses RLS. Use sparingly.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    future=True,
)

# Separate engine for RLS-bypassing work (migrations, seeds, admin bootstrap,
# cross-tenant scheduler scans). In the compose stack this connects as the DB
# owner while the app engine connects as the restricted `app_user` role.
privileged_engine = create_engine(
    settings.privileged_sqlalchemy_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
PrivilegedSessionLocal = sessionmaker(
    bind=privileged_engine, autoflush=False, expire_on_commit=False, future=True
)


@contextmanager
def tenant_session(firm_id: uuid.UUID | str) -> Generator[Session]:
    """Yield a session scoped to a single firm via RLS.

    Sets ``app.current_firm_id`` for the life of the transaction. Every query
    the caller runs is transparently filtered to this firm by the RLS policies
    defined in the migrations. The GUC is set with ``set_config(..., is_local=true)``
    so it is scoped to this transaction and cleared on commit/rollback.
    """
    session = SessionLocal()
    try:
        session.execute(
            text("SELECT set_config('app.current_firm_id', :firm_id, true)"),
            {"firm_id": str(firm_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def privileged_session() -> Generator[Session]:
    """Yield a session that bypasses RLS. Bootstrap / seeding / admin /
    cross-tenant scheduler scans only.

    Connects via the privileged engine (DB owner / BYPASSRLS role), not the
    restricted app role. Never expose this to a normal request handler.
    """
    session = PrivilegedSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
