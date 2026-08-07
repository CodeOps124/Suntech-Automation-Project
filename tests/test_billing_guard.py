"""Billing guardrail tests — the pricing non-negotiables from CLAUDE.md §1/§6."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.constants import MIN_ENTRY_PLAN_PRICE_INR, PLAN_CATALOG, PlanTier
from app.services.billing import (
    FORBIDDEN_LINE_ITEMS,
    BillingRuleViolation,
    price_change_guard,
)


class TestForbiddenLineItems:
    @pytest.mark.parametrize("item", sorted(FORBIDDEN_LINE_ITEMS))
    def test_forbidden_items_always_raise(self, item):
        with pytest.raises(BillingRuleViolation):
            price_change_guard(item)

    def test_ca_certification_fee_is_forbidden(self):
        # The single most likely way to make the business unprofitable (Doc A).
        assert "ca_certification_fee" in FORBIDDEN_LINE_ITEMS

    def test_udin_bank_fx_and_opinion_are_forbidden(self):
        assert {
            "udin_generation",
            "bank_remittance_charge",
            "fx_spread",
            "tax_opinion",
        } <= FORBIDDEN_LINE_ITEMS


class TestEntryPriceFloor:
    def test_entry_plan_below_floor_raises(self):
        with pytest.raises(BillingRuleViolation, match="cannot be sold below"):
            price_change_guard("plan_ca_starter", Decimal("24999"))

    def test_entry_plan_at_floor_passes(self):
        price_change_guard("plan_ca_starter", MIN_ENTRY_PLAN_PRICE_INR)

    def test_normal_line_items_pass(self):
        price_change_guard("onboarding_setup", Decimal("50000"))


class TestPlanCatalog:
    def test_catalog_matches_doc_b_pricing(self):
        expected = {
            PlanTier.CA_STARTER: ("25000", 25, "700"),
            PlanTier.CA_GROWTH: ("60000", 100, "550"),
            PlanTier.CA_PRO: ("120000", 300, "400"),
            PlanTier.CA_ENTERPRISE: ("250000", 800, "300"),
            PlanTier.CA_NETWORK: ("500000", 2000, "200"),
        }
        for tier, (price, included, extra) in expected.items():
            entry = PLAN_CATALOG[tier]
            assert entry["monthly_price_inr"] == Decimal(price)
            assert entry["included_remittances"] == included
            assert entry["extra_remittance_inr"] == Decimal(extra)

    def test_no_plan_below_entry_floor(self):
        for entry in PLAN_CATALOG.values():
            assert entry["monthly_price_inr"] >= MIN_ENTRY_PLAN_PRICE_INR
