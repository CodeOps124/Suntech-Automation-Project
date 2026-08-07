"""Document checklist / gap detection.

Given a case's Part classification and the documents already on file, decide
which required documents are still missing. A gap sends the case to
`pending_documents` and drives the reminder scheduler (§10, §16 step 8).

Requirements are intentionally simple and data-driven here; the later
document-understanding layer (§14) can refine them, but the deterministic core
must have a defensible baseline.
"""

from __future__ import annotations

from app.core.constants import DocumentType, PartClassification
from app.models.case import Case

# Baseline required document types per Part. Part D (exempt) needs the least;
# Part C (CA certificate path) needs the full evidentiary set.
REQUIRED_DOCS: dict[PartClassification, set[DocumentType]] = {
    PartClassification.PART_A: {DocumentType.INVOICE},
    PartClassification.PART_B: {DocumentType.INVOICE, DocumentType.AO_CERTIFICATE},
    PartClassification.PART_C: {
        DocumentType.INVOICE,
        DocumentType.AGREEMENT,
        DocumentType.TRC,
        DocumentType.FORM_10F,
        DocumentType.NO_PE_DECLARATION,
    },
    PartClassification.PART_D: {DocumentType.INVOICE},
}


def missing_documents(case: Case) -> list[DocumentType]:
    """Return required doc types not yet present on the case (empty = complete)."""
    if not case.part_classification:
        # Not classified yet — can't compute a meaningful checklist.
        return []
    part = PartClassification(case.part_classification)
    required = REQUIRED_DOCS.get(part, {DocumentType.INVOICE})
    present = {DocumentType(d.doc_type) for d in case.documents if _is_known(d.doc_type)}
    return sorted(required - present, key=lambda d: d.value)


def _is_known(doc_type: str) -> bool:
    try:
        DocumentType(doc_type)
        return True
    except ValueError:
        return False
