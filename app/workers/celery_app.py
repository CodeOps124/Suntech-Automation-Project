"""Celery application. OCR/validation run async, never on the request path.

Beat schedule drives the document-reminder cadence (§13 reminder scheduler).
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

celery_app = Celery(
    "suntech_form145",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",          # Indian CA firms; FY and reminders align to IST
    enable_utc=True,
    task_acks_late=True,              # a killed worker re-queues, doesn't lose the case
    worker_prefetch_multiplier=1,
    task_default_retry_delay=30,
)

celery_app.conf.beat_schedule = {
    # Document-gap chasing: hourly scan; the task itself enforces the
    # per-case reminder interval and the included-reminder cap.
    "chase-document-gaps": {
        "task": "app.workers.tasks.send_document_reminders",
        "schedule": crontab(minute=0),
    },
}
