"""FastAPI dependencies — tenant context resolution.

Dev-grade tenancy: the caller sends `X-Firm-ID`. Every request-scoped session
comes from tenant_session(), so RLS scopes all queries to that firm even if a
route handler forgets a WHERE clause.

TODO(auth): replace the raw header with JWT auth (python-jose + passlib are
already in the dependency set): token carries firm_id + user_id + role, and
this dependency validates it and derives the firm from the token, never from
client input.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, tenant_session
from app.models.firm import Firm


def get_firm_id(x_firm_id: str = Header(...)) -> uuid.UUID:
    try:
        return uuid.UUID(x_firm_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Firm-ID must be a UUID",
        ) from exc


def get_db(firm_id: uuid.UUID = Depends(get_firm_id)) -> Iterator[Session]:
    """Tenant-scoped session. RLS active for the life of the request."""
    with tenant_session(firm_id) as session:
        yield session


def get_current_firm(
    firm_id: uuid.UUID = Depends(get_firm_id),
) -> Firm:
    """Load the firm row itself (firms is not RLS-scoped; validate it exists)."""
    session = SessionLocal()
    try:
        firm = session.get(Firm, firm_id)
        if firm is None:
            raise HTTPException(status_code=404, detail="firm not found")
        return firm
    finally:
        session.close()
