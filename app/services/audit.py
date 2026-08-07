"""Case state transitions + append-only audit logging.

Every status change goes through `transition()`, which:
  * validates the move against ALLOWED_TRANSITIONS (state machine),
  * blocks automation from entering a human-only state (§1 non-negotiable),
  * updates cases.status,
  * writes a case_events row (append-only).

`log_event()` records non-transition events (OCR done, classified, reminder
sent, warning raised) to the same trail.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.constants import (
    ALLOWED_TRANSITIONS,
    HUMAN_ONLY_TARGET_STATES,
    CaseStatus,
    EventType,
)
from app.models.case import Case, CaseEvent


class TransitionError(Exception):
    """Raised on an illegal state move or a human-only guard violation."""


def log_event(
    session: Session,
    case: Case,
    event_type: EventType,
    *,
    message: str | None = None,
    detail: dict | None = None,
    actor_user_id: uuid.UUID | None = None,
    old_status: str | None = None,
    new_status: str | None = None,
) -> CaseEvent:
    event = CaseEvent(
        firm_id=case.firm_id,
        case_id=case.id,
        actor_user_id=actor_user_id,
        event_type=event_type.value,
        old_status=old_status,
        new_status=new_status,
        message=message,
        detail=detail,
    )
    session.add(event)
    session.flush()
    return event


def transition(
    session: Session,
    case: Case,
    to_status: CaseStatus,
    *,
    actor_user_id: uuid.UUID | None = None,
    by_automation: bool = True,
    message: str | None = None,
    detail: dict | None = None,
) -> None:
    """Move a case to `to_status`, validating and auditing the move.

    `by_automation=True` (the default) means the pipeline/worker is the actor.
    Entering a human-only state (certified, filed) with by_automation=True is a
    hard error — that is the guard protecting the CA-stays-human rule.
    """
    from_status = CaseStatus(case.status)

    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise TransitionError(
            f"illegal transition {from_status.value} -> {to_status.value}"
        )

    if by_automation and to_status in HUMAN_ONLY_TARGET_STATES:
        raise TransitionError(
            f"transition into {to_status.value} requires a human actor; "
            f"automation may not certify or file (CLAUDE.md §1)"
        )

    old = case.status
    case.status = to_status.value
    session.add(case)

    log_event(
        session,
        case,
        EventType.STATUS_CHANGED,
        message=message or f"{old} → {to_status.value}",
        detail=detail,
        actor_user_id=actor_user_id,
        old_status=old,
        new_status=to_status.value,
    )
