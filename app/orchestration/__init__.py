"""Orchestrated / intelligent pipeline — build-order step 10 (STUB, later-stage).

CLAUDE.md §14: an enhancement layer AROUND the deterministic core, added only
once that core is solid in production. Interfaces are sketched here so the
seams exist; nothing in the current pipeline imports this package.

Layout (when built):
    document_understanding.py — LLM reads messy documents (scanned agreements,
        mixed-language invoices) and emits structured chargeability /
        AO-certificate signals for the classifier's INPUT. It supplies inputs;
        it NEVER decides the Part.
    exception_triage.py — LLM flags unusual cases (odd vendor structure,
        conflicting documents) to a human tax specialist instead of proceeding.
    orchestrator.py — coordinates: understanding -> deterministic rules
        (app.rules.classifier, unchanged) -> triage -> CA handoff/audit
        (app.services.audit, unchanged).

Hard boundaries carried over from §14:
  * classification stays in app.rules.classifier — an LLM never assigns Part A–D
  * audit logging stays deterministic and append-only
  * certification stays human
"""
