"""FastAPI application entrypoint.

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app import __version__
from app.api.routes import admin, auth, cases, dashboard, directory, documents, internal
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def _verify_app_role_is_restricted() -> None:
    """RLS is the tenant boundary — a superuser/BYPASSRLS app role silently
    disables it. Hard-fail outside dev; loud warning in dev."""
    from app.db.session import engine

    try:
        with engine.connect() as conn:
            bypasses = conn.execute(
                text(
                    "SELECT rolsuper OR rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            ).scalar()
    except Exception as exc:
        logger.warning("rls_role_check_skipped", error=str(exc))
        return

    if bypasses:
        message = (
            "app database role is superuser/BYPASSRLS — row-level security is "
            "NOT enforced. Point DATABASE_URL at the restricted app_user role "
            "(created by migration 0003)."
        )
        if settings.app_env == "dev":
            logger.warning("rls_not_enforced", detail=message)
        else:
            raise RuntimeError(message)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _verify_app_role_is_restricted()
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version=__version__,
    description=(
        "Suntech Business Solutions — workflow automation for Form 145/146 "
        "(15CA/15CB) remittance filings, sold to CA firms. The platform prepares; "
        "the CA certifies. Certification is never automated."
    ),
)

app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(admin.router, prefix=settings.api_v1_prefix)
app.include_router(directory.router, prefix=settings.api_v1_prefix)
app.include_router(cases.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
app.include_router(documents.router, prefix=settings.api_v1_prefix)
app.include_router(internal.router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "app": settings.app_name, "version": __version__}


@app.get(settings.api_v1_prefix + "/meta", tags=["meta"])
def meta():
    """Public facts the sign in page needs before anyone has signed in.
    Deliberately limited to the environment name and version."""
    return {"environment": settings.app_env, "version": __version__}


# ---- SunComply 145 web app (review dashboard, §15) --------------------------
WEB_DIR = Path(__file__).parent / "web" / "static"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

# ---- Standalone product demo (scripted, no backend calls) -------------------
# Also runs without this server: `python -m http.server` inside demo/.
DEMO_DIR = Path(__file__).parent.parent / "demo"
if DEMO_DIR.exists():
    app.mount("/demo", StaticFiles(directory=DEMO_DIR, html=True), name="demo")


@app.get("/", include_in_schema=False)
def web_app():
    return FileResponse(WEB_DIR / "index.html")
