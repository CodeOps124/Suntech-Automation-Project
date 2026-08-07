"""Password hashing and session tokens.

Scope note. This is working demo authentication for the pilot build: real
password verification, real signed tokens, wrong credentials rejected. The
production hardening steps (token verification middleware on every route,
refresh flow, lockout, password policy) are listed in the README roadmap and
are not claimed here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

TOKEN_TTL_HOURS = 12
ALGORITHM = "HS256"

# bcrypt hashes at most 72 bytes of input. Longer passwords are truncated to
# that boundary on both hash and verify so the two paths always agree.
_BCRYPT_MAX_BYTES = 72


def _to_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_to_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_session_token(*, user_id: str, firm_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "firm_id": firm_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_session_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
