"""Document routes at firm level.

The E-Invoices module lists every uploaded document across cases and serves
the file content for viewing and download. Listing and access are scoped to
the signed in firm by row level security, same as every other route.

Files are streamed through the API rather than exposed as storage URLs, so
the object store never needs to be reachable from the browser.
"""

from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.case import Document
from app.schemas.case import DocumentRead
from app.storage.s3 import download_fileobj

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentRead])
def list_all_documents(
    doc_type: str | None = None,
    session: Session = Depends(get_db),
):
    stmt = select(Document).order_by(Document.created_at.desc())
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    return session.execute(stmt).scalars().all()


@router.get("/{document_id}/file")
def get_document_file(document_id: uuid.UUID, session: Session = Depends(get_db)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")

    buffer = io.BytesIO()
    try:
        download_fileobj(document.storage_path, buffer)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="storage read failed") from exc

    filename = document.original_filename or "document.bin"
    return Response(
        content=buffer.getvalue(),
        media_type=document.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
