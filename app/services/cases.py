"""Case service — create, certify, file. Business logic above the ORM.

Certification (`certify_case`) is the one place a human, and only a human,
moves a case into `certified`. It requires a DSC reference and UDIN and records
the acting CA user. Automation cannot reach this function's effect because
`transition(..., by_automation=False)` is the only way into a human-only state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.constants import CaseStatus, EventType, UserRole
from app.models.case import Case
from app.models.firm import FirmUser
from app.services.audit import TransitionError, log_event, transition


class CertificationError(Exception):
    pass


def create_case(
    session: Session,
    *,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
    vendor_id: uuid.UUID | None,
    amount=None,
    currency: str | None = None,
    purpose_code: str | None = None,
    remittance_date=None,
) -> Case:
    case = Case(
        firm_id=firm_id,
        client_id=client_id,
        vendor_id=vendor_id,
        status=CaseStatus.INTAKE.value,
        amount=amount,
        currency=currency,
        purpose_code=purpose_code,
        remittance_date=remittance_date,
    )
    session.add(case)
    session.flush()
    log_event(
        session,
        case,
        EventType.CASE_CREATED,
        message="case created (intake)",
        new_status=CaseStatus.INTAKE.value,
    )
    return case


def certify_case(
    session: Session,
    case: Case,
    *,
    actor_user: FirmUser,
    dsc_reference: str,
    udin: str,
) -> Case:
    """Human CA certifies the case. Never called by automation.

    Guards:
      * the case must be ready_for_review,
      * the actor must be a ca_reviewer (or admin),
      * DSC reference and UDIN are mandatory.
    """
    if case.status != CaseStatus.READY_FOR_REVIEW.value:
        raise CertificationError(
            f"case must be {CaseStatus.READY_FOR_REVIEW.value} to certify, "
            f"is {case.status}"
        )
    if actor_user.role not in (UserRole.CA_REVIEWER.value, UserRole.ADMIN.value):
        raise CertificationError(
            f"user role '{actor_user.role}' may not certify; requires ca_reviewer"
        )
    if not dsc_reference.strip() or not udin.strip():
        raise CertificationError("DSC reference and UDIN are both required")

    case.dsc_reference = dsc_reference.strip()
    case.udin = udin.strip()
    case.certified_by_user_id = actor_user.id
    case.certified_at = datetime.now(timezone.utc)

    # by_automation=False — the ONLY sanctioned way into a human-only state.
    transition(
        session,
        case,
        CaseStatus.CERTIFIED,
        actor_user_id=actor_user.id,
        by_automation=False,
        message=f"certified by {actor_user.name}",
        detail={"udin": udin, "dsc_reference": dsc_reference},
    )
    log_event(
        session,
        case,
        EventType.CERTIFIED,
        actor_user_id=actor_user.id,
        message="CA certification recorded (DSC + UDIN)",
        detail={"udin": udin},
    )
    return case


def mark_filed(
    session: Session,
    case: Case,
    *,
    actor_user: FirmUser,
) -> Case:
    """Record that the client/CA filed Form 145. Filing support only — the
    platform never files on the portal itself (§17)."""
    if case.status != CaseStatus.CERTIFIED.value:
        raise TransitionError("only a certified case can be marked filed")
    transition(
        session,
        case,
        CaseStatus.FILED,
        actor_user_id=actor_user.id,
        by_automation=False,
        message=f"marked filed by {actor_user.name}",
    )
    log_event(session, case, EventType.FILED, actor_user_id=actor_user.id, message="Form 145 filed")
    return case
