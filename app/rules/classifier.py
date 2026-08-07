"""Deterministic Form 145 Part A/B/C/D classifier.

This is a PURE function (CLAUDE.md §1, §11): no LLM, no DB access, no I/O. It
takes an immutable input and returns an immutable result. The caller is
responsible for loading the per-vendor FY aggregate and passing it in — that
keeps this function unit-testable in complete isolation from the database.

Every result carries the rule version that produced it, plus reason codes and
evidence (§7.1 step 5: "must retain reason codes and evidence"). The classifier
NEVER decides certification — it only routes the case to a Part; a human CA
still reviews and signs Part C.

Decision tree (§11):

    1. Chargeable to tax?  (DTAA + Rule 37BB(3) exemptions)
         No  -> Part D  (exempt, no CA certificate)
         Yes -> 2
    2. Aggregate to this vendor, this FY, <= ₹5,00,000?
         Yes -> Part A  (basic declaration)
         No  -> 3
    3. AO lower/nil-TDS certificate (Section 195/197) on file?
         Yes -> Part B
         No  -> Part C  (needs Form 146 — CA certificate)

Separately, a case-level WARNING (not a branch): specified transactions whose
aggregate exceeds ₹10,00,000 in the FY may trigger 20% TCS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.core.constants import (
    PART_A_FY_AGGREGATE_THRESHOLD_INR,
    TCS_WARNING_RATE,
    TCS_WARNING_THRESHOLD_INR,
    PartClassification,
)

# The version of THIS rule set. Must match a row in `rule_versions` and
# settings.active_rule_version. Bump on any change to the logic below, and
# add a new rule_versions row — never edit a shipped version's behaviour.
RULE_VERSION = "2024.1"


@dataclass(frozen=True)
class ClassificationInput:
    """Everything the classifier needs, resolved by the caller beforehand.

    Amounts are in INR. `prior_fy_aggregate_to_vendor_inr` is the total already
    remitted to this vendor earlier in the same financial year (excluding the
    current remittance); the classifier adds the current amount itself.
    """

    is_chargeable_to_tax: bool
    current_amount_inr: Decimal
    prior_fy_aggregate_to_vendor_inr: Decimal = Decimal("0")
    has_ao_certificate: bool = False
    is_specified_transaction: bool = False  # e.g. LRS overseas investment (TCS check)


@dataclass(frozen=True)
class ClassificationResult:
    part: PartClassification
    rule_version: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_ca_certificate: bool = False  # True only for Part C

    def as_dict(self) -> dict:
        return {
            "part": self.part.value,
            "rule_version": self.rule_version,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "requires_ca_certificate": self.requires_ca_certificate,
        }


def _tcs_warnings(inp: ClassificationInput, fy_aggregate: Decimal) -> list[str]:
    warnings: list[str] = []
    if inp.is_specified_transaction and fy_aggregate > TCS_WARNING_THRESHOLD_INR:
        pct = int(TCS_WARNING_RATE * 100)
        warnings.append(
            f"TCS_WARNING: specified-transaction FY aggregate "
            f"₹{fy_aggregate:,} exceeds ₹{TCS_WARNING_THRESHOLD_INR:,.0f}; "
            f"{pct}% TCS may apply. Surface to CA — not a classification branch."
        )
    return warnings


def classify(inp: ClassificationInput) -> ClassificationResult:
    """Route a remittance to Part A/B/C/D. Pure and deterministic."""
    fy_aggregate = inp.prior_fy_aggregate_to_vendor_inr + inp.current_amount_inr
    warnings = _tcs_warnings(inp, fy_aggregate)

    # Step 1 — chargeability.
    if not inp.is_chargeable_to_tax:
        return ClassificationResult(
            part=PartClassification.PART_D,
            rule_version=RULE_VERSION,
            reasons=[
                "NOT_CHARGEABLE: payment not chargeable to tax (DTAA / Rule 37BB(3) exemption)."
            ],
            warnings=warnings,
            requires_ca_certificate=False,
        )

    # Step 2 — per-vendor FY aggregate threshold.
    if fy_aggregate <= PART_A_FY_AGGREGATE_THRESHOLD_INR:
        return ClassificationResult(
            part=PartClassification.PART_A,
            rule_version=RULE_VERSION,
            reasons=[
                f"AGGREGATE_WITHIN_THRESHOLD: FY aggregate to vendor "
                f"₹{fy_aggregate:,} ≤ ₹{PART_A_FY_AGGREGATE_THRESHOLD_INR:,.0f}; "
                f"basic declaration (Part A)."
            ],
            warnings=warnings,
            requires_ca_certificate=False,
        )

    # Step 3 — AO certificate?
    if inp.has_ao_certificate:
        return ClassificationResult(
            part=PartClassification.PART_B,
            rule_version=RULE_VERSION,
            reasons=[
                f"AO_CERTIFICATE_ON_FILE: FY aggregate ₹{fy_aggregate:,} exceeds threshold "
                f"but a lower/nil-TDS AO order (Sec 195/197) is on file; Part B."
            ],
            warnings=warnings,
            requires_ca_certificate=False,
        )

    return ClassificationResult(
        part=PartClassification.PART_C,
        rule_version=RULE_VERSION,
        reasons=[
            f"REQUIRES_FORM_146: FY aggregate ₹{fy_aggregate:,} exceeds threshold, "
            f"no AO certificate; Form 146 (CA certificate) required before Form 145 filing."
        ],
        warnings=warnings,
        requires_ca_certificate=True,
    )
