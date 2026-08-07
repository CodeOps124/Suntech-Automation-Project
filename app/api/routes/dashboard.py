"""Review dashboard data routes (§15).

Serves the stat cards, the pipeline view, and the activity feed. The MVP
frontend polls these every few seconds; SSE/websockets only if polling ever
becomes a real load problem (§15 — explicitly not before).
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_firm
from app.core.constants import CaseStatus
from app.models.case import Case, CaseEvent
from app.models.firm import Firm
from app.schemas.case import CaseEventRead, DashboardStats
from app.services.billing import month_usage

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# States where automation is actively working the case.
AUTOMATION_STATES = {
    CaseStatus.INTAKE.value,
    CaseStatus.EXTRACTING.value,
    CaseStatus.VALIDATING.value,
    CaseStatus.PENDING_DOCUMENTS.value,
}


def _today_start() -> datetime:
    return datetime.combine(date.today(), time.min, tzinfo=timezone.utc)


@router.get("/stats", response_model=DashboardStats)
def stats(session: Session = Depends(get_db)):
    by_status: dict[str, int] = dict(
        session.execute(select(Case.status, func.count(Case.id)).group_by(Case.status)).all()
    )
    cases_today = session.execute(
        select(func.count(Case.id)).where(Case.created_at >= _today_start())
    ).scalar_one()
    filed_today = session.execute(
        select(func.count(CaseEvent.id))
        .where(CaseEvent.new_status == CaseStatus.FILED.value)
        .where(CaseEvent.created_at >= _today_start())
    ).scalar_one()

    return DashboardStats(
        cases_today=cases_today,
        in_automation=sum(by_status.get(s, 0) for s in AUTOMATION_STATES),
        awaiting_ca_review=by_status.get(CaseStatus.READY_FOR_REVIEW.value, 0),
        filed_today=filed_today,
        by_status=by_status,
    )


@router.get("/activity", response_model=list[CaseEventRead])
def activity(limit: int = 50, session: Session = Depends(get_db)):
    """Recent automated actions — case_events rendered as a feed (§15)."""
    stmt = select(CaseEvent).order_by(CaseEvent.created_at.desc()).limit(min(limit, 200))
    return session.execute(stmt).scalars().all()


@router.get("/usage")
def usage(
    firm: Firm = Depends(get_current_firm),
    session: Session = Depends(get_db),
):
    """This month's remittance count vs. plan allowance + overage estimate."""
    return month_usage(session, firm)


@router.get("/system")
def system_info(_: Session = Depends(get_db)):
    """Runtime facts for the Settings screen. No secrets. The session
    dependency is only here so the route requires a valid firm header."""
    from app import __version__
    from app.core.config import settings as cfg

    return {
        "version": __version__,
        "environment": cfg.app_env,
        "rule_version": cfg.active_rule_version,
        "pipeline_driver": getattr(cfg, "pipeline_driver", "celery"),
        "ocr_provider": cfg.ocr_provider,
        "reminder_interval_hours": cfg.reminder_interval_hours,
        "reminder_max_included": cfg.reminder_max_included,
    }
