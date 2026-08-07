"""Internal pipeline-step endpoints — the surface n8n orchestrates.

Each endpoint is a thin wrapper over the SAME services the Celery driver uses
(audit/state machine, classifier, checklist). No business logic lives here and
none lives in n8n: n8n sequences these calls and displays the run; Postgres,
RLS, and the versioned rules engine enforce everything.

Auth: every call requires the X-Internal-Token shared secret (the app hands it
to n8n inside the webhook payload; n8n echoes it back) AND the normal X-Firm-ID
tenant header, so all queries run under RLS exactly like user traffic.

State gating makes every step idempotent-safe: a retry that arrives after the
step already ran gets a 409 and n8n stops cleanly instead of double-running.
"""

from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.constants import CaseStatus, EventType
from app.core.logging import get_logger
from app.models.case import Case
from app.services.audit import log_event, transition
from app.services.checklist import missing_documents
from app.services.classification import classify_case
from app.storage.s3 import download_fileobj
from app.workers.ocr import get_ocr_provider
from app.workers.tasks import MIN_EXTRACTION_CONFIDENCE

logger = get_logger(__name__)


def verify_internal_token(x_internal_token: str = Header(...)) -> None:
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=401, detail="invalid internal token")


router = APIRouter(
    prefix="/internal/cases",
    tags=["internal-pipeline"],
    dependencies=[Depends(verify_internal_token)],
    include_in_schema=False,  # not part of the public API surface
)


def _claim_case(session: Session, case_id: uuid.UUID, expected_status: CaseStatus) -> Case:
    """Row-lock the case and require it to be in the expected state (else 409)."""
    case = session.execute(
        select(Case).where(Case.id == case_id).with_for_update()
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    if case.status != expected_status.value:
        raise HTTPException(
            status_code=409,
            detail=f"case is '{case.status}', step requires '{expected_status.value}'",
        )
    return case


@router.post("/{case_id}/extract")
def step_extract(case_id: uuid.UUID, session: Session = Depends(get_db)):
    """intake → extracting → validating. OCR every document, score confidence."""
    case = _claim_case(session, case_id, CaseStatus.INTAKE)
    transition(session, case, CaseStatus.EXTRACTING, message="OCR extraction started (n8n)")

    provider = get_ocr_provider()
    low_confidence = False
    extracted = 0
    for document in case.documents:
        buffer = io.BytesIO()
        download_fileobj(document.storage_path, buffer)
        result = provider.extract(buffer.getvalue(), document.original_filename or "file")
        document.confidence_score = result.confidence
        document.extracted_data = {"fields": result.fields, "provider": settings.ocr_provider}
        session.add(document)
        log_event(
            session, case, EventType.OCR_COMPLETED,
            message=f"OCR complete for {document.original_filename} "
                    f"(confidence {result.confidence:.2f})",
            detail={"document_id": str(document.id), "confidence": result.confidence},
        )
        extracted += 1
        if result.confidence < MIN_EXTRACTION_CONFIDENCE:
            low_confidence = True

    transition(session, case, CaseStatus.VALIDATING, message="validation started (n8n)")

    if low_confidence:
        transition(session, case, CaseStatus.EXCEPTION,
                   message="low extraction confidence — routed to human triage")
        log_event(session, case, EventType.EXCEPTION_RAISED,
                  message=f"document(s) below confidence {MIN_EXTRACTION_CONFIDENCE}")
        return {"proceed": False, "result": "exception:low_confidence",
                "documents_extracted": extracted}

    return {"proceed": True, "result": "validating", "documents_extracted": extracted}


@router.post("/{case_id}/revalidate")
def step_revalidate(case_id: uuid.UUID, session: Session = Depends(get_db)):
    """pending_documents → validating, after new documents arrive."""
    case = _claim_case(session, case_id, CaseStatus.PENDING_DOCUMENTS)
    transition(session, case, CaseStatus.VALIDATING, message="re-validating after upload (n8n)")
    return {"proceed": True, "result": "validating"}


@router.post("/{case_id}/classify")
def step_classify(case_id: uuid.UUID, session: Session = Depends(get_db)):
    """Run the deterministic rules engine. The ONLY classification path —
    n8n never carries a copy of these rules."""
    case = _claim_case(session, case_id, CaseStatus.VALIDATING)

    if case.amount is None or case.vendor_id is None:
        transition(session, case, CaseStatus.EXCEPTION,
                   message="missing amount or vendor — cannot classify; routed to human triage")
        log_event(session, case, EventType.EXCEPTION_RAISED,
                  message="classification blocked: amount/vendor not captured")
        return {"proceed": False, "result": "exception:missing_fields"}

    has_ao_cert = any(d.doc_type == "ao_certificate" for d in case.documents)
    part = classify_case(session, case, has_ao_certificate=has_ao_cert)
    return {"proceed": True, "result": "classified", "part": part.value,
            "requires_ca_certificate": part.value == "C"}


@router.post("/{case_id}/checklist")
def step_checklist(case_id: uuid.UUID, session: Session = Depends(get_db)):
    """validating → pending_documents (gaps) or ready_for_review (complete)."""
    case = _claim_case(session, case_id, CaseStatus.VALIDATING)

    gaps = missing_documents(case)
    if gaps:
        transition(session, case, CaseStatus.PENDING_DOCUMENTS,
                   message=f"missing documents: {', '.join(g.value for g in gaps)}",
                   detail={"missing": [g.value for g in gaps]})
        log_event(session, case, EventType.DOCUMENT_GAP_DETECTED,
                  message=f"{len(gaps)} document(s) missing",
                  detail={"missing": [g.value for g in gaps]})
        return {"proceed": False, "result": "pending_documents",
                "missing": [g.value for g in gaps]}

    transition(session, case, CaseStatus.READY_FOR_REVIEW,
               message="pack complete — awaiting CA review (automation stops here)")
    return {"proceed": True, "result": "ready_for_review"}
