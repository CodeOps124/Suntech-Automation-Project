"""Usage metering and plan guardrails.

Sells workflow software ONLY (CLAUDE.md §1). This module must never contain a
line item for CA certification fees, UDIN generation, bank charges, FX spread,
or tax opinions — those belong to the CA firm and its client. The explicit
FORBIDDEN_LINE_ITEMS list exists so a future billing feature fails loudly if
someone tries to price them in.

MVP scope: count cases against the plan's included monthly remittances and
price overage at the plan's per-remittance rate. Invoicing/payment collection
is out of scope for the scaffold.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import MIN_ENTRY_PLAN_PRICE_INR, PLAN_CATALOG, PlanTier
from app.models.case import Case
from app.models.firm import Firm

# Never price these into the platform. Guard checked by price_change_guard().
FORBIDDEN_LINE_ITEMS: frozenset[str] = frozenset(
    {
        "ca_certification_fee",
        "udin_generation",
        "bank_remittance_charge",
        "fx_spread",
        "tax_opinion",
    }
)


class BillingRuleViolation(Exception):
    pass


def price_change_guard(line_item_code: str, amount_inr: Decimal | None = None) -> None:
    """Call before adding any billable line item. Raises on forbidden items
    and on entry-plan pricing below the ₹25,000 floor."""
    if line_item_code in FORBIDDEN_LINE_ITEMS:
        raise BillingRuleViolation(
            f"'{line_item_code}' can never be a platform line item (CLAUDE.md §1)"
        )
    if (
        line_item_code == "plan_ca_starter"
        and amount_inr is not None
        and amount_inr < MIN_ENTRY_PLAN_PRICE_INR
    ):
        raise BillingRuleViolation(
            f"entry plan cannot be sold below ₹{MIN_ENTRY_PLAN_PRICE_INR:,.0f}/month"
        )


def _month_start(today: date | None = None) -> datetime:
    today = today or date.today()
    return datetime(today.year, today.month, 1, tzinfo=timezone.utc)


def month_usage(session: Session, firm: Firm) -> dict:
    """Cases opened this calendar month vs. the firm's plan allowance."""
    plan = PlanTier(firm.plan_tier)
    catalog = PLAN_CATALOG[plan]
    used = session.execute(
        select(func.count(Case.id)).where(Case.created_at >= _month_start())
    ).scalar_one()

    included = int(catalog["included_remittances"])
    overage_count = max(0, used - included)
    overage_rate = Decimal(str(catalog["extra_remittance_inr"]))

    return {
        "plan": plan.value,
        "monthly_price_inr": str(catalog["monthly_price_inr"]),
        "included_remittances": included,
        "used_this_month": used,
        "overage_count": overage_count,
        "overage_rate_inr": str(overage_rate),
        "overage_charge_inr": str(overage_rate * overage_count),
    }
