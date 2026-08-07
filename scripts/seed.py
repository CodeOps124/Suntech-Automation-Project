"""Seed the database with the Suntech Business Solutions demo firm.

    python -m scripts.seed            # local venv
    docker compose run --rm api python -m scripts.seed

Idempotent: re-running finds the existing firm by name and leaves it alone.

Creates:
  * rule_versions row "2024.1" (active) — matches app.rules.classifier.RULE_VERSION
  * firm "Suntech Business Solutions" on CA Growth
  * three users (admin / analyst / ca_reviewer)
  * two clients, three foreign vendors
  * demo cases spread across pipeline states, with audit events — enough for
    the dashboard to look alive on first boot

Demo cases are seeded directly via the service layer (not the HTTP API), and
classification runs through the real rules engine, so seeded data is exactly
what the pipeline would have produced.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.core.constants import CaseStatus, PlanTier, UserRole
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.session import privileged_session, tenant_session
from app.models.case import Case
from app.models.client import Client, Vendor
from app.models.firm import Firm, FirmUser
from app.models.rule_version import RuleVersion
from app.rules.classifier import RULE_VERSION
from app.services.audit import transition
from app.services.cases import certify_case, create_case
from app.services.classification import classify_case

configure_logging()
logger = get_logger(__name__)

FIRM_NAME = "Suntech Business Solutions"
DEMO_PASSWORD = "suntech123"


def seed_rule_version() -> None:
    with privileged_session() as session:
        existing = session.execute(
            select(RuleVersion).where(RuleVersion.version == RULE_VERSION)
        ).scalar_one_or_none()
        if existing:
            logger.info("rule_version_exists", version=RULE_VERSION)
            return
        session.add(
            RuleVersion(
                version=RULE_VERSION,
                description="Initial Part A/B/C/D rule set per CLAUDE.md §11 "
                            "(₹5L FY aggregate threshold, AO certificate branch, "
                            "₹10L TCS warning).",
                is_active=True,
            )
        )
        logger.info("rule_version_created", version=RULE_VERSION)


def seed_firm() -> str | None:
    """Create the demo firm + users. Returns firm id, or None if it existed."""
    with privileged_session() as session:
        existing = session.execute(
            select(Firm).where(Firm.name == FIRM_NAME)
        ).scalar_one_or_none()
        if existing:
            logger.info("firm_exists", firm_id=str(existing.id))
            return None

        firm = Firm(name=FIRM_NAME, plan_tier=PlanTier.CA_GROWTH.value)
        session.add(firm)
        session.flush()

        # Every demo user signs in with the same demo password. This is pilot
        # credentialing, stated openly in the README; production auth policy
        # is on the roadmap.
        demo_hash = hash_password(DEMO_PASSWORD)
        for name, email, role in (
            ("Suntech Admin", "admin@suntech.example", UserRole.ADMIN),
            ("Priya Analyst", "priya@suntech.example", UserRole.ANALYST),
            ("CA Ramesh Iyer", "ramesh@suntech.example", UserRole.CA_REVIEWER),
        ):
            session.add(
                FirmUser(
                    firm_id=firm.id,
                    name=name,
                    email=email,
                    role=role.value,
                    hashed_password=demo_hash,
                )
            )

        firm_id = str(firm.id)
    logger.info("firm_created", firm_id=firm_id)
    return firm_id


def seed_cases(firm_id: str) -> None:
    with tenant_session(firm_id) as session:
        acme = Client(firm_id=firm_id, name="Acme Exports Pvt Ltd", pan="AAACA1234F")
        zenith = Client(firm_id=firm_id, name="Zenith Software Ltd", pan="AAACZ9876K")
        session.add_all([acme, zenith])
        session.flush()

        gulf = Vendor(
            firm_id=firm_id, client_id=acme.id, name="Gulf Machinery Trading LLC",
            country="United Arab Emirates", tin="TRN100234567890",
        )
        stripe_ie = Vendor(
            firm_id=firm_id, client_id=zenith.id, name="CloudStack Ireland Ltd",
            country="Ireland", tin="IE6388047V",
        )
        sg_consult = Vendor(
            firm_id=firm_id, client_id=zenith.id, name="Meridian Consulting Pte Ltd",
            country="Singapore", tin="201812345K",
        )
        session.add_all([gulf, stripe_ie, sg_consult])
        session.flush()

        reviewer = session.execute(
            select(FirmUser).where(FirmUser.role == UserRole.CA_REVIEWER.value)
        ).scalars().first()

        # 1) Fresh intake — small machinery invoice (would classify Part A).
        create_case(
            session, firm_id=firm_id, client_id=acme.id, vendor_id=gulf.id,
            amount=Decimal("310000"), currency="AED", purpose_code="S0101",
        )

        # 2) Classified, waiting on documents — big software licence (Part C path).
        c2 = create_case(
            session, firm_id=firm_id, client_id=zenith.id, vendor_id=stripe_ie.id,
            amount=Decimal("2150000"), currency="EUR", purpose_code="S0802",
        )
        transition(session, c2, CaseStatus.EXTRACTING, message="OCR extraction started")
        transition(session, c2, CaseStatus.VALIDATING, message="validation started")
        classify_case(session, c2)
        transition(
            session, c2, CaseStatus.PENDING_DOCUMENTS,
            message="missing documents: agreement, trc, form_10f, no_pe_declaration",
        )

        # 3) Ready for CA review — consulting fees above threshold (Part C).
        c3 = create_case(
            session, firm_id=firm_id, client_id=zenith.id, vendor_id=sg_consult.id,
            amount=Decimal("900000"), currency="SGD", purpose_code="S1006",
        )
        transition(session, c3, CaseStatus.EXTRACTING, message="OCR extraction started")
        transition(session, c3, CaseStatus.VALIDATING, message="validation started")
        classify_case(session, c3)
        transition(session, c3, CaseStatus.READY_FOR_REVIEW,
                   message="pack complete — awaiting CA review")

        # 4) Certified + filed — the full happy path, certified by the CA user.
        c4 = create_case(
            session, firm_id=firm_id, client_id=acme.id, vendor_id=gulf.id,
            amount=Decimal("480000"), currency="AED", purpose_code="S0101",
        )
        transition(session, c4, CaseStatus.EXTRACTING, message="OCR extraction started")
        transition(session, c4, CaseStatus.VALIDATING, message="validation started")
        classify_case(session, c4)
        transition(session, c4, CaseStatus.READY_FOR_REVIEW,
                   message="pack complete — awaiting CA review")
        if reviewer:
            certify_case(
                session, c4, actor_user=reviewer,
                dsc_reference="DSC-DEMO-2026-0001",
                udin="26123456AKTUAL1234",
            )

    logger.info("cases_seeded", firm_id=firm_id)


def main() -> None:
    seed_rule_version()
    firm_id = seed_firm()
    if firm_id is None:
        logger.info("seed_skipped", reason="firm already present")
        return
    seed_cases(firm_id)
    print(f"\nSeed complete. Demo firm id: {firm_id}")
    print("Use it as the X-Firm-ID header when calling the API.")


if __name__ == "__main__":
    main()
