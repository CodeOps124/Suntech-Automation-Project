"""Case routes — intake, document upload, review actions, audit trail.

Upload lands the file in object storage and queues the async pipeline; the
request never blocks on OCR (§2). Certification and filing endpoints are the
human actions from the review dashboard.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_firm_id
from app.core.constants import CaseStatus, DocumentType, EventType
from app.models.case import Case, CaseEvent, Document
from app.models.client import Client, Vendor
from app.models.firm import FirmUser
from app.schemas.case import CaseCreate, CaseEventRead, CaseRead, CertifyRequest, DocumentRead
from app.services.audit import TransitionError, log_event
from app.services.bank_pack import generate_bank_pack_pdf
from app.services.cases import CertificationError, certify_case, create_case, mark_filed
from app.storage.s3 import build_key, upload_fileobj
from app.services.dispatch import dispatch_pipeline

router = APIRouter(prefix="/cases", tags=["cases"])


def _get_case_or_404(session: Session, case_id: uuid.UUID) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@router.post("", response_model=CaseRead, status_code=201)
def open_case(
    payload: CaseCreate,
    firm_id: uuid.UUID = Depends(get_firm_id),
    session: Session = Depends(get_db),
):
    """Open a case (one remittance). Files are uploaded separately."""
    # Resolve references under the tenant session: RLS hides other firms'
    # rows, so a cross-tenant client/vendor id 404s instead of being linked.
    client = session.get(Client, payload.client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    if payload.vendor_id is not None:
        vendor = session.get(Vendor, payload.vendor_id)
        if vendor is None:
            raise HTTPException(status_code=404, detail="vendor not found")
        if vendor.client_id != payload.client_id:
            raise HTTPException(
                status_code=422, detail="vendor does not belong to this client"
            )

    case = create_case(
        session,
        firm_id=firm_id,
        client_id=payload.client_id,
        vendor_id=payload.vendor_id,
        amount=payload.amount,
        currency=payload.currency,
        purpose_code=payload.purpose_code,
        remittance_date=payload.remittance_date,
    )
    return case


@router.get("", response_model=list[CaseRead])
def list_cases(
    status_filter: str | None = None,
    session: Session = Depends(get_db),
):
    stmt = select(Case).order_by(Case.created_at.desc())
    if status_filter:
        stmt = stmt.where(Case.status == status_filter)
    return session.execute(stmt).scalars().all()


@router.get("/{case_id}", response_model=CaseRead)
def get_case(case_id: uuid.UUID, session: Session = Depends(get_db)):
    return _get_case_or_404(session, case_id)


@router.post("/{case_id}/documents", response_model=DocumentRead, status_code=201)
def upload_document(
    case_id: uuid.UUID,
    file: UploadFile = File(...),
    doc_type: DocumentType = Form(DocumentType.OTHER),
    firm_id: uuid.UUID = Depends(get_firm_id),
    session: Session = Depends(get_db),
):
    """Attach a document: store the file, record the row, queue the pipeline.

    On an intake case this starts processing; on a pending_documents case it
    triggers re-validation. OCR runs async — this request returns immediately.
    """
    case = _get_case_or_404(session, case_id)

    document = Document(
        firm_id=firm_id,
        case_id=case.id,
        doc_type=doc_type.value,
        storage_path="",  # set after we know the document id
        original_filename=file.filename,
        content_type=file.content_type,
    )
    session.add(document)
    session.flush()

    key = build_key(firm_id, case.id, document.id, file.filename or "upload.bin")
    upload_fileobj(file.file, key, content_type=file.content_type)
    document.storage_path = key
    session.add(document)

    log_event(
        session,
        case,
        EventType.DOCUMENT_UPLOADED,
        message=f"uploaded {file.filename} as {doc_type.value}",
        detail={"document_id": str(document.id), "doc_type": doc_type.value},
    )
    case_status = case.status

    # Commit BEFORE queueing: otherwise the worker can race the request
    # transaction and read stale state (no document row yet). The commit also
    # clears the transaction-local RLS GUC, so no DB reads after this point.
    session.commit()

    # Kick off async processing — never on the request path. The configured
    # driver (Celery or n8n) sequences the pipeline; services enforce it.
    if case_status == CaseStatus.INTAKE.value:
        dispatch_pipeline(firm_id, case.id, "intake")
    elif case_status == CaseStatus.PENDING_DOCUMENTS.value:
        dispatch_pipeline(firm_id, case.id, "revalidate")

    return document


@router.get("/{case_id}/documents", response_model=list[DocumentRead])
def list_documents(case_id: uuid.UUID, session: Session = Depends(get_db)):
    _get_case_or_404(session, case_id)
    stmt = (
        select(Document)
        .where(Document.case_id == case_id)
        .order_by(Document.created_at.asc())
    )
    return session.execute(stmt).scalars().all()


@router.get("/{case_id}/events", response_model=list[CaseEventRead])
def case_events(case_id: uuid.UUID, session: Session = Depends(get_db)):
    """Full append-only history for one case — the §15 activity feed."""
    _get_case_or_404(session, case_id)
    stmt = (
        select(CaseEvent)
        .where(CaseEvent.case_id == case_id)
        .order_by(CaseEvent.created_at.asc())
    )
    return session.execute(stmt).scalars().all()


@router.post("/{case_id}/certify", response_model=CaseRead)
def certify(
    case_id: uuid.UUID,
    payload: CertifyRequest,
    session: Session = Depends(get_db),
):
    """HUMAN action: CA certifies with DSC reference + UDIN.

    This endpoint is the review dashboard's approve button. It is the only
    path into `certified`, and the service layer enforces role + references.
    """
    case = _get_case_or_404(session, case_id)
    actor = session.get(FirmUser, payload.actor_user_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="actor user not found")
    try:
        return certify_case(
            session,
            case,
            actor_user=actor,
            dsc_reference=payload.dsc_reference,
            udin=payload.udin,
        )
    except CertificationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{case_id}/bank-pack")
def bank_pack(case_id: uuid.UUID, session: Session = Depends(get_db)):
    """Download the bank-ready PDF pack (certified/filed cases only)."""
    case = _get_case_or_404(session, case_id)
    try:
        pdf_bytes = generate_bank_pack_pdf(case)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="bank-pack-{case_id}.pdf"'},
    )


@router.post("/{case_id}/file", response_model=CaseRead)
def file_case(
    case_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    session: Session = Depends(get_db),
):
    """HUMAN action: record that Form 145 was filed (filing support only —
    the platform never touches the government portal, §17)."""
    case = _get_case_or_404(session, case_id)
    actor = session.get(FirmUser, actor_user_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="actor user not found")
    try:
        return mark_filed(session, case, actor_user=actor)
    except TransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
