"""Rules engine tests — the §11 decision tree, exhaustively.

The classifier is pure, so these tests need no database, no network, nothing.
If any of these fail after a rules change, that change needs a NEW rule
version, not an edit to 2024.1.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.constants import PartClassification
from app.rules.classifier import RULE_VERSION, ClassificationInput, classify


def make_input(**overrides) -> ClassificationInput:
    defaults = dict(
        is_chargeable_to_tax=True,
        current_amount_inr=Decimal("100000"),
        prior_fy_aggregate_to_vendor_inr=Decimal("0"),
        has_ao_certificate=False,
        is_specified_transaction=False,
    )
    defaults.update(overrides)
    return ClassificationInput(**defaults)


class TestPartD:
    def test_not_chargeable_is_part_d(self):
        result = classify(make_input(is_chargeable_to_tax=False))
        assert result.part is PartClassification.PART_D
        assert result.requires_ca_certificate is False

    def test_not_chargeable_wins_even_over_huge_amounts(self):
        result = classify(
            make_input(is_chargeable_to_tax=False, current_amount_inr=Decimal("99000000"))
        )
        assert result.part is PartClassification.PART_D


class TestPartA:
    def test_small_single_remittance_is_part_a(self):
        result = classify(make_input(current_amount_inr=Decimal("100000")))
        assert result.part is PartClassification.PART_A

    def test_aggregate_exactly_at_threshold_is_part_a(self):
        # Boundary: ≤ ₹5,00,000 stays Part A.
        result = classify(
            make_input(
                current_amount_inr=Decimal("200000"),
                prior_fy_aggregate_to_vendor_inr=Decimal("300000"),
            )
        )
        assert result.part is PartClassification.PART_A

    def test_prior_aggregate_counts_toward_threshold(self):
        # 4.9L prior + 2L current = 6.9L -> not Part A.
        result = classify(
            make_input(
                current_amount_inr=Decimal("200000"),
                prior_fy_aggregate_to_vendor_inr=Decimal("490000"),
            )
        )
        assert result.part is not PartClassification.PART_A


class TestPartBAndC:
    def test_over_threshold_with_ao_certificate_is_part_b(self):
        result = classify(
            make_input(current_amount_inr=Decimal("600000"), has_ao_certificate=True)
        )
        assert result.part is PartClassification.PART_B
        assert result.requires_ca_certificate is False

    def test_over_threshold_without_ao_certificate_is_part_c(self):
        result = classify(make_input(current_amount_inr=Decimal("600000")))
        assert result.part is PartClassification.PART_C
        assert result.requires_ca_certificate is True

    def test_one_rupee_over_threshold_is_not_part_a(self):
        result = classify(make_input(current_amount_inr=Decimal("500000.01")))
        assert result.part is PartClassification.PART_C


class TestTCSWarning:
    def test_specified_transaction_over_10l_warns(self):
        result = classify(
            make_input(
                current_amount_inr=Decimal("1100000"),
                is_specified_transaction=True,
            )
        )
        assert any("TCS_WARNING" in w for w in result.warnings)
        # Warning must NOT change the branch (it's Part C here on merits).
        assert result.part is PartClassification.PART_C

    def test_specified_transaction_under_10l_does_not_warn(self):
        result = classify(
            make_input(
                current_amount_inr=Decimal("900000"),
                is_specified_transaction=True,
            )
        )
        assert result.warnings == []

    def test_non_specified_transaction_never_warns(self):
        result = classify(make_input(current_amount_inr=Decimal("5000000")))
        assert result.warnings == []

    def test_warning_present_even_on_part_d(self):
        # Exempt cases can still carry the TCS warning — it is orthogonal.
        result = classify(
            make_input(
                is_chargeable_to_tax=False,
                current_amount_inr=Decimal("1500000"),
                is_specified_transaction=True,
            )
        )
        assert result.part is PartClassification.PART_D
        assert any("TCS_WARNING" in w for w in result.warnings)


class TestDeterminismAndProvenance:
    def test_every_result_carries_rule_version(self):
        for inp in (
            make_input(),
            make_input(is_chargeable_to_tax=False),
            make_input(current_amount_inr=Decimal("600000")),
            make_input(current_amount_inr=Decimal("600000"), has_ao_certificate=True),
        ):
            assert classify(inp).rule_version == RULE_VERSION

    def test_same_input_same_output(self):
        inp = make_input(current_amount_inr=Decimal("600000"))
        first = classify(inp)
        for _ in range(10):
            again = classify(inp)
            assert again.part is first.part
            assert again.reasons == first.reasons

    def test_reasons_always_present(self):
        assert classify(make_input()).reasons


@pytest.mark.parametrize(
    ("chargeable", "amount", "prior", "ao", "expected"),
    [
        (False, "100", "0", False, PartClassification.PART_D),
        (True, "500000", "0", False, PartClassification.PART_A),
        (True, "500001", "0", False, PartClassification.PART_C),
        (True, "500001", "0", True, PartClassification.PART_B),
        (True, "1", "500000", False, PartClassification.PART_C),
        (False, "500001", "0", True, PartClassification.PART_D),  # step 1 wins
    ],
)
def test_decision_table(chargeable, amount, prior, ao, expected):
    result = classify(
        make_input(
            is_chargeable_to_tax=chargeable,
            current_amount_inr=Decimal(amount),
            prior_fy_aggregate_to_vendor_inr=Decimal(prior),
            has_ao_certificate=ao,
        )
    )
    assert result.part is expected
