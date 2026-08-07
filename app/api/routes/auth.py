"""Sign in for firm users.

The web app calls this once at login. A valid email and password return the
user profile, the firm workspace, and a signed session token. The password
check is real bcrypt verification against firm_users.hashed_password and a
wrong password is rejected.

Lookup runs on the privileged session because login happens before a firm
context exists. Nothing here can write data.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from app.core.security import create_session_token, verify_password
from app.db.session import privileged_session
from app.models.firm import Firm, FirmUser

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
def login(payload: LoginRequest):
    with privileged_session() as session:
        user = session.execute(
            select(FirmUser).where(FirmUser.email == payload.email.lower())
        ).scalars().first()

        if user is None or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        firm = session.get(Firm, user.firm_id)
        if firm is None:
            raise HTTPException(status_code=401, detail="Workspace not found")

        token = create_session_token(
            user_id=str(user.id), firm_id=str(firm.id), role=user.role
        )
        return {
            "token": token,
            "user": {
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "role": user.role,
            },
            "firm": {
                "id": str(firm.id),
                "name": firm.name,
                "plan_tier": firm.plan_tier,
            },
        }
