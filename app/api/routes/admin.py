"""Platform-admin bootstrap routes — create firms and their first users.

These use the privileged (RLS-bypassing) session because a firm cannot create
itself. In production this surface must sit behind platform-operator auth,
separate from firm-user auth. Dev scaffold: unauthenticated, localhost only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from app.core.constants import PLAN_CATALOG, PlanTier, UserRole
from app.db.session import privileged_session
from app.models.firm import Firm, FirmUser

router = APIRouter(prefix="/admin", tags=["admin"])


class FirmCreate(BaseModel):
    name: str
    plan_tier: PlanTier = PlanTier.CA_STARTER


class FirmUserCreate(BaseModel):
    name: str
    email: EmailStr
    role: UserRole = UserRole.ANALYST


@router.post("/firms", status_code=201)
def create_firm(payload: FirmCreate):
    if payload.plan_tier not in PLAN_CATALOG:
        raise HTTPException(status_code=422, detail="unknown plan tier")
    with privileged_session() as session:
        firm = Firm(name=payload.name, plan_tier=payload.plan_tier.value)
        session.add(firm)
        session.flush()
        return {"id": str(firm.id), "name": firm.name, "plan_tier": firm.plan_tier}


@router.post("/firms/{firm_id}/users", status_code=201)
def create_firm_user(firm_id: uuid.UUID, payload: FirmUserCreate):
    with privileged_session() as session:
        firm = session.get(Firm, firm_id)
        if firm is None:
            raise HTTPException(status_code=404, detail="firm not found")
        user = FirmUser(
            firm_id=firm_id,
            name=payload.name,
            email=payload.email,
            role=payload.role.value,
        )
        session.add(user)
        session.flush()
        return {"id": str(user.id), "email": user.email, "role": user.role}
