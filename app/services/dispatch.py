"""Pipeline dispatch — one place that decides HOW a case gets processed.

PIPELINE_DRIVER=celery : queue the in-process Celery task (default).
PIPELINE_DRIVER=n8n    : fire the n8n intake webhook; n8n then drives the case
                         through the /internal endpoints. If the webhook can't
                         be reached, fall back to Celery and note it in the
                         audit trail — orchestrator downtime must never strand
                         a case in intake.

Both paths execute the same service layer; the driver only chooses the
sequencer.
"""

from __future__ import annotations

import uuid

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def dispatch_pipeline(firm_id: uuid.UUID | str, case_id: uuid.UUID | str, mode: str) -> str:
    """Kick off processing for a case. mode: 'intake' | 'revalidate'.
    Returns the driver that actually took the job ('n8n' or 'celery')."""
    if settings.pipeline_driver == "n8n" and settings.n8n_webhook_url:
        try:
            response = httpx.post(
                settings.n8n_webhook_url,
                json={
                    "firm_id": str(firm_id),
                    "case_id": str(case_id),
                    "mode": mode,
                    "token": settings.internal_api_token,
                },
                timeout=5.0,
            )
            response.raise_for_status()
            logger.info("pipeline_dispatched", driver="n8n", case_id=str(case_id), mode=mode)
            return "n8n"
        except Exception as exc:
            logger.error(
                "n8n_dispatch_failed_falling_back_to_celery",
                case_id=str(case_id), error=str(exc),
            )

    from app.workers.tasks import process_case, revalidate_case

    task = process_case if mode == "intake" else revalidate_case
    task.delay(str(firm_id), str(case_id))
    logger.info("pipeline_dispatched", driver="celery", case_id=str(case_id), mode=mode)
    return "celery"
