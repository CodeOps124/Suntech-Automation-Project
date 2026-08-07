"""Domain constants and enums.

These encode business rules that must NOT drift silently:
  - Case lifecycle states (CLAUDE.md §10)
  - Part A/B/C/D classification labels (§11)
  - CA-firm plan pricing (§6.1) — the ONLY pricing this product sells
  - User roles, document types, event types

Certification fees, bank charges, and tax opinions are deliberately absent
here: the platform never prices them (a §1 non-negotiable).
"""

from __future__ import annotations

import enum
from decimal import Decimal


class CaseStatus(str, enum.Enum):
    """Case lifecycle, in order. See CLAUDE.md §10.

    intake -> extracting -> validating -> pending_documents (loops) ->
    ready_for_review -> certified (HUMAN ONLY) -> filed
    """

    INTAKE = "intake"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    PENDING_DOCUMENTS = "pending_documents"
    READY_FOR_REVIEW = "ready_for_review"
    CERTIFIED = "certified"          # never set by automation — human action only
    FILED = "filed"
    # Off-happy-path:
    EXCEPTION = "exception"          # sent to a human tax specialist (triage)


# Legal forward transitions. Enforced in the pipeline; anything else is a bug.
ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.INTAKE: {CaseStatus.EXTRACTING, CaseStatus.EXCEPTION},
    CaseStatus.EXTRACTING: {CaseStatus.VALIDATING, CaseStatus.EXCEPTION},
    CaseStatus.VALIDATING: {
        CaseStatus.PENDING_DOCUMENTS,
        CaseStatus.READY_FOR_REVIEW,
        CaseStatus.EXCEPTION,
    },
    CaseStatus.PENDING_DOCUMENTS: {
        CaseStatus.VALIDATING,          # re-validate once docs arrive
        CaseStatus.READY_FOR_REVIEW,
        CaseStatus.EXCEPTION,
    },
    CaseStatus.READY_FOR_REVIEW: {CaseStatus.CERTIFIED, CaseStatus.EXCEPTION},
    CaseStatus.CERTIFIED: {CaseStatus.FILED},
    CaseStatus.FILED: set(),
    CaseStatus.EXCEPTION: {CaseStatus.VALIDATING, CaseStatus.READY_FOR_REVIEW},
}

# States a human — not automation — is the only actor allowed to move a case
# *into*. Guards the §1 non-negotiable: CA certification stays human.
HUMAN_ONLY_TARGET_STATES: frozenset[CaseStatus] = frozenset(
    {CaseStatus.CERTIFIED, CaseStatus.FILED}
)


class PartClassification(str, enum.Enum):
    """Form 145 Part, per the deterministic rule engine (CLAUDE.md §11)."""

    PART_A = "A"  # basic declaration (aggregate <= 5L this FY, chargeable)
    PART_B = "B"  # AO lower/nil-TDS certificate on file
    PART_C = "C"  # needs Form 146 (CA certificate)
    PART_D = "D"  # not chargeable to tax — exempt


class UserRole(str, enum.Enum):
    ANALYST = "analyst"
    CA_REVIEWER = "ca_reviewer"
    ADMIN = "admin"


class DocumentType(str, enum.Enum):
    INVOICE = "invoice"
    AGREEMENT = "agreement"
    TRC = "trc"                        # tax residency certificate
    FORM_10F = "form_10f"
    NO_PE_DECLARATION = "no_pe_declaration"
    AO_CERTIFICATE = "ao_certificate"  # lower/nil TDS order (Section 195/197)
    OTHER = "other"


class EventType(str, enum.Enum):
    """case_events.event_type — append-only audit trail."""

    CASE_CREATED = "case_created"
    STATUS_CHANGED = "status_changed"
    OCR_COMPLETED = "ocr_completed"
    CLASSIFIED = "classified"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_GAP_DETECTED = "document_gap_detected"
    REMINDER_SENT = "reminder_sent"
    CERTIFIED = "certified"
    FILED = "filed"
    EXCEPTION_RAISED = "exception_raised"
    WARNING_RAISED = "warning_raised"


class PlanTier(str, enum.Enum):
    """CA-firm subscription plans. See CLAUDE.md §6.1 (Doc B)."""

    CA_STARTER = "ca_starter"
    CA_GROWTH = "ca_growth"
    CA_PRO = "ca_pro"
    CA_ENTERPRISE = "ca_enterprise"
    CA_NETWORK = "ca_network"


# CA-firm plan pricing (INR/month) and included monthly remittances.
# This is the ONLY pricing model the product sells (Doc B). Never below
# ₹25,000/month for the entry plan.
PLAN_CATALOG: dict[PlanTier, dict[str, Decimal | int]] = {
    PlanTier.CA_STARTER: {
        "monthly_price_inr": Decimal("25000"),
        "included_remittances": 25,
        "extra_remittance_inr": Decimal("700"),
    },
    PlanTier.CA_GROWTH: {
        "monthly_price_inr": Decimal("60000"),
        "included_remittances": 100,
        "extra_remittance_inr": Decimal("550"),
    },
    PlanTier.CA_PRO: {
        "monthly_price_inr": Decimal("120000"),
        "included_remittances": 300,
        "extra_remittance_inr": Decimal("400"),
    },
    PlanTier.CA_ENTERPRISE: {
        "monthly_price_inr": Decimal("250000"),
        "included_remittances": 800,
        "extra_remittance_inr": Decimal("300"),
    },
    PlanTier.CA_NETWORK: {
        "monthly_price_inr": Decimal("500000"),
        "included_remittances": 2000,
        "extra_remittance_inr": Decimal("200"),
    },
}

# Entry-price floor — a §6.1 non-negotiable. Any billing code MUST refuse to
# sell the entry plan below this.
MIN_ENTRY_PLAN_PRICE_INR: Decimal = Decimal("25000")

# Threshold constants used by the rules engine (CLAUDE.md §11).
PART_A_FY_AGGREGATE_THRESHOLD_INR: Decimal = Decimal("500000")     # ≤ ₹5L -> Part A
TCS_WARNING_THRESHOLD_INR: Decimal = Decimal("1000000")            # > ₹10L -> 20% TCS warning
TCS_WARNING_RATE: Decimal = Decimal("0.20")
