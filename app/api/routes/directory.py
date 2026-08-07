"""Directory routes — clients and vendors for the current firm."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_firm_id
from app.models.client import Client, Vendor
from app.models.firm import FirmUser
from app.schemas.case import ClientCreate, ClientRead, UserRead, VendorCreate, VendorRead

router = APIRouter(tags=["directory"])


@router.get("/users", response_model=list[UserRead])
def list_users(session: Session = Depends(get_db)):
    """Firm staff (RLS-scoped) — drives the 'acting as' selector in the UI."""
    return session.execute(select(FirmUser).order_by(FirmUser.name)).scalars().all()


@router.post("/clients", response_model=ClientRead, status_code=201)
def create_client(
    payload: ClientCreate,
    firm_id: uuid.UUID = Depends(get_firm_id),
    session: Session = Depends(get_db),
):
    client = Client(firm_id=firm_id, name=payload.name, pan=payload.pan)
    session.add(client)
    session.flush()
    return client


@router.get("/clients", response_model=list[ClientRead])
def list_clients(session: Session = Depends(get_db)):
    return session.execute(select(Client).order_by(Client.name)).scalars().all()


@router.post("/vendors", response_model=VendorRead, status_code=201)
def create_vendor(
    payload: VendorCreate,
    firm_id: uuid.UUID = Depends(get_firm_id),
    session: Session = Depends(get_db),
):
    client = session.get(Client, payload.client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    vendor = Vendor(
        firm_id=firm_id,
        client_id=payload.client_id,
        name=payload.name,
        country=payload.country,
        tin=payload.tin,
        trc_valid_until=payload.trc_valid_until,
    )
    session.add(vendor)
    session.flush()
    return vendor


@router.get("/vendors", response_model=list[VendorRead])
def list_vendors(
    client_id: uuid.UUID | None = None,
    session: Session = Depends(get_db),
):
    stmt = select(Vendor).order_by(Vendor.name)
    if client_id:
        stmt = stmt.where(Vendor.client_id == client_id)
    return session.execute(stmt).scalars().all()
