"""Celery tasks — the automated case pipeline and the reminder scheduler.

Pipeline (CLAUDE.md §10): intake -> extracting -> validating ->
pending_documents | ready_for_review. Automation STOPS at ready_for_review;
certification and filing are human actions in the review dashboard.

Every task takes (firm_id, case_id) and opens a tenant_session so RLS scopes
all queries to the owning firm. Every hop writes case_events.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.constants import CaseStatus, EventType
from app.core.logging import get_logger
from app.db.session import privileged_session, tenant_session
from app.models.case import Case
from app.services.audit import log_event, transition
from app.services.checklist import missing_documents
from app.services.classification import classify_case
from app.storage.s3 import download_fileobj
from app.workers.celery_app import celery_app
from app.workers.ocr import get_ocr_provider

logger = get_logger(__name__)

# Extraction below this confidence sends the case to exception triage instead
# of proceeding silently (§7.1 step 2: confidence scoring).
MIN_EXTRACTION_CONFIDENCE = 0.85


@celery_app.task(bind=True, max_retries=3)
def process_case(self, firm_id: str, case_id: str) -> str:
    """Run one case through extraction -> validation -> classification."""
    with tenant_session(firm_id) as session:
        # Row lock claims the case: a duplicate delivery blocks here, then sees
        # the status has moved on and skips — no double pipeline runs.
        case = session.execute(
            select(Case).where(Case.id == case_id).with_for_update()
        ).scalar_one_or_none()
        if case is None:
            logger.warning("case_not_found", case_id=case_id)
            return "not_found"
        if case.status != CaseStatus.INTAKE.value:
            logger.info("case_not_in_intake", case_id=case_id, status=case.status)
            return f"skipped:{case.status}"

        # --- intake -> extracting -------------------------------------------
        transition(session, case, CaseStatus.EXTRACTING, message="OCR extraction started")

        provider = get_ocr_provider()
        low_confidence = False
        for document in case.documents:
            buffer = io.BytesIO()
            try:
                download_fileobj(document.storage_path, buffer)
            except Exception as exc:  # storage hiccup — retry the whole task
                logger.error("document_download_failed", key=document.storage_path, error=str(exc))
                raise self.retry(exc=exc)

            result = provider.extract(buffer.getvalue(), document.original_filename or "file")
            document.confidence_score = result.confidence
            document.extracted_data = {
                "fields": result.fields,
                "provider": settings.ocr_provider,
            }
            session.add(document)
            log_event(
                session,
                case,
                EventType.OCR_COMPLETED,
                message=f"OCR complete for {document.original_filename} "
                        f"(confidence {result.confidence:.2f})",
                detail={"document_id": str(document.id), "confidence": result.confidence},
            )
            if result.confidence < MIN_EXTRACTION_CONFIDENCE:
                low_confidence = True

        # --- extracting -> validating ---------------------------------------
        transition(session, case, CaseStatus.VALIDATING, message="validation started")

        if low_confidence:
            transition(
                session,
                case,
                CaseStatus.EXCEPTION,
                message="low extraction confidence — routed to human triage",
            )
            log_event(
                session,
                case,
                EventType.EXCEPTION_RAISED,
                message=f"one or more documents below confidence {MIN_EXTRACTION_CONFIDENCE}",
            )
            return "exception:low_confidence"

        # A case without an amount or vendor cannot be classified against the
        # per-vendor FY threshold — send it to a human, never to a tax branch.
        if case.amount is None or case.vendor_id is None:
            transition(
                session,
                case,
                CaseStatus.EXCEPTION,
                message="missing amount or vendor — cannot classify; routed to human triage",
            )
            log_event(
                session,
                case,
                EventType.EXCEPTION_RAISED,
                message="classification blocked: amount/vendor not captured",
            )
            return "exception:missing_fields"

        # --- classification (deterministic rules engine) --------------------
        # AO certificate presence is derived from uploaded documents; the
        # chargeability flag defaults to True (conservative) until the
        # document-understanding layer (§14) supplies a real signal.
        has_ao_cert = any(d.doc_type == "ao_certificate" for d in case.documents)
        classify_case(session, case, has_ao_certificate=has_ao_cert)

        # --- document checklist ---------------------------------------------
        gaps = missing_documents(case)
        if gaps:
            transition(
                session,
                case,
                CaseStatus.PENDING_DOCUMENTS,
                message=f"missing documents: {', '.join(g.value for g in gaps)}",
                detail={"missing": [g.value for g in gaps]},
            )
            log_event(
                session,
                case,
                EventType.DOCUMENT_GAP_DETECTED,
                message=f"{len(gaps)} document(s) missing",
                detail={"missing": [g.value for g in gaps]},
            )
            return "pending_documents"

        # --- ready for the human CA -----------------------------------------
        transition(
            session,
            case,
            CaseStatus.READY_FOR_REVIEW,
            message="pack complete — awaiting CA review (automation stops here)",
        )
        return "ready_for_review"


@celery_app.task
def revalidate_case(firm_id: str, case_id: str) -> str:
    """Re-run classification + checklist after new documents arrive.

    Classification must re-run, not just the checklist: an AO certificate
    uploaded while pending should move the case Part C -> Part B.
    """
    with tenant_session(firm_id) as session:
        case = session.execute(
            select(Case).where(Case.id == case_id).with_for_update()
        ).scalar_one_or_none()
        if case is None or case.status != CaseStatus.PENDING_DOCUMENTS.value:
            return "skipped"
        transition(session, case, CaseStatus.VALIDATING, message="re-validating after upload")

        if case.amount is None or case.vendor_id is None:
            transition(
                session,
                case,
                CaseStatus.EXCEPTION,
                message="missing amount or vendor — cannot classify; routed to human triage",
            )
            return "exception:missing_fields"

        has_ao_cert = any(d.doc_type == "ao_certificate" for d in case.documents)
        classify_case(session, case, has_ao_certificate=has_ao_cert)

        gaps = missing_documents(case)
        if gaps:
            transition(
                session,
                case,
                CaseStatus.PENDING_DOCUMENTS,
                message=f"still missing: {', '.join(g.value for g in gaps)}",
            )
            return "pending_documents"
        transition(session, case, CaseStatus.READY_FOR_REVIEW,
                   message="documents complete — awaiting CA review")
        return "ready_for_review"


@celery_app.task
def send_document_reminders() -> int:
    """Beat task: chase document gaps on pending cases (§16 step 8).

    Caps included reminders per case (REMINDER_MAX_INCLUDED) — beyond the cap
    the chasing becomes billable rework (§9: limit included reminders), so we
    log a WARNING_RAISED instead of another reminder.

    Runs across firms, so it uses a plain session for the scan but a
    tenant_session per case for the writes. Sending is a log-only stub until
    an email/WhatsApp provider is wired in.
    """
    interval = timedelta(hours=settings.reminder_interval_hours)
    now = datetime.now(timezone.utc)
    sent = 0

    # Scan needs cross-tenant visibility: use the privileged path deliberately.
    with privileged_session() as scan:
        pending = scan.execute(
            select(Case.id, Case.firm_id).where(
                Case.status == CaseStatus.PENDING_DOCUMENTS.value
            )
        ).all()

    for case_id, firm_id in pending:
        with tenant_session(firm_id) as session:
            case = session.get(Case, case_id)
            if case is None:
                continue

            reminders = [
                e for e in case.events if e.event_type == EventType.REMINDER_SENT.value
            ]
            if reminders:
                last = max(e.created_at for e in reminders)
                if now - last < interval:
                    continue
            if len(reminders) >= settings.reminder_max_included:
                log_event(
                    session,
                    case,
                    EventType.WARNING_RAISED,
                    message=f"included reminder cap ({settings.reminder_max_included}) "
                            f"reached — further chasing is billable rework",
                )
                continue

            # TODO(email/WhatsApp provider): actually send. Log-only for now.
            log_event(
                session,
                case,
                EventType.REMINDER_SENT,
                message=f"document reminder {len(reminders) + 1} of "
                        f"{settings.reminder_max_included} sent",
            )
            sent += 1

    logger.info("reminders_sent", count=sent)
    return sent
