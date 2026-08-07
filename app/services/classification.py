"""Classification service — bridges the pure rules engine to the database.

Responsibilities the pure classifier deliberately does NOT have:
  * resolve the per-vendor per-FY prior aggregate from `cases`,
  * decide chargeability inputs (here: a conservative placeholder until the
    document-understanding layer supplies real DTAA/exemption signals),
  * persist the Part, the rule_version_id, and the reason/evidence blob,
  * record CLASSIFIED and any WARNING_RAISED events.

The classification decision itself stays 100% in app.rules.classifier.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.constants import EventType, PartClassification
from app.models.case import Case
from app.models.rule_version import RuleVersion
from app.rules.classifier import ClassificationInput, classify
from app.services.audit import log_event


def fy_bounds(anchor: date) -> tuple[date, date]:
    """Indian financial year containing `anchor`: 1 April – 31 March."""
    year = anchor.year if anchor.month >= 4 else anchor.year - 1
    return date(year, 4, 1), date(year + 1, 3, 31)


def _anchor_date(case: Case) -> date:
    """The date that decides which FY a case belongs to.

    remittance_date when captured; created_at otherwise. Never wall-clock
    "today" — a March case classified in April must stay in the old FY.
    """
    if case.remittance_date is not None:
        return case.remittance_date
    return case.created_at.date()


def _prior_fy_aggregate_to_vendor(session: Session, case: Case) -> Decimal:
    """Sum of other remittance amounts to this vendor in the case's own FY.

    Excludes the current case; bounded at both FY ends. Each prior case is
    bucketed by its own anchor date (remittance_date, else created_at). RLS
    already scopes this to the firm.
    """
    if case.vendor_id is None:
        return Decimal("0")

    fy_start, fy_end = fy_bounds(_anchor_date(case))
    effective_date = func.coalesce(Case.remittance_date, func.date(Case.created_at))
    stmt = (
        select(Case.amount)
        .where(Case.vendor_id == case.vendor_id)       
        .where(Case.id != case.id)
        .where(effective_date >= fy_start)
        .where(effective_date <= fy_end)
        .where(Case.amount.isnot(None))
    )
    total = Decimal("0")
    for (amount,) in session.execute(stmt).all():
        total += Decimal(str(amount))
    return total


def _resolve_active_rule_version(session: Session) -> RuleVersion | None:
    return session.execute(
        select(RuleVersion).where(RuleVersion.is_active.is_(True))
    ).scalar_one_or_none()


def classify_case(
    session: Session,
    case: Case,
    *,
    is_chargeable_to_tax: bool = True,
    has_ao_certificate: bool = False,
    is_specified_transaction: bool = False,
) -> PartClassification:
    """Classify a case, persist the result, and audit it.

    Chargeability / AO-certificate / specified-transaction flags are inputs the
    caller supplies (from extracted documents or ops review). Defaults are
    conservative: chargeable=True routes ambiguous cases toward CA review
    rather than silently exempting them.
    """
    # Serialize concurrent classifications for the same vendor+FY: without
    # this, two in-flight cases can each see the other's amount missing from
    # the aggregate and both land under the Part A threshold. The advisory
    # lock is transaction-scoped and keyed on (vendor, FY).
    if case.vendor_id is not None:
        fy_start, _ = fy_bounds(_anchor_date(case))
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"classify:{case.vendor_id}:{fy_start.isoformat()}"},
        )

    prior = _prior_fy_aggregate_to_vendor(session, case)
    # TODO(fx): case.amount may be in a foreign currency; the ₹5L/₹10L
    # thresholds are INR. Convert at the applicable rate before comparing —
    # exchange-rate mismatch is one of the filing errors this product exists
    # to fix (CLAUDE.md §3). Until an FX source is wired, amounts are treated
    # as INR, which over-counts foreign-currency cases toward Part C — the
    # conservative direction (more CA review, never less).
    result = classify(
        ClassificationInput(
            is_chargeable_to_tax=is_chargeable_to_tax,
            current_amount_inr=Decimal(str(case.amount or 0)),
            prior_fy_aggregate_to_vendor_inr=prior,
            has_ao_certificate=has_ao_certificate,
            is_specified_transaction=is_specified_transaction,
        )
    )

    rule_row = _resolve_active_rule_version(session)
    case.part_classification = result.part.value
    case.rule_version_id = rule_row.id if rule_row else None
    case.classification_reasons = result.as_dict()
    session.add(case)

    log_event(
        session,
        case,
        EventType.CLASSIFIED,
        message=f"classified as Part {result.part.value} (rules {result.rule_version})",
        detail=result.as_dict(),
    )

    for warning in result.warnings:
        log_event(
            session,
            case,
            EventType.WARNING_RAISED,
            message=warning,
            detail={"warning": warning},
        )

    return result.part
