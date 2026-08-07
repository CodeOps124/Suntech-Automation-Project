"""Bank-ready PDF package generation — build-order step 9 (STUB).

Assembles a cover summary of the case (client, vendor, amount, purpose code,
Part classification, UDIN) into a single PDF the client hands to their bank/AD.
Deliberately last in the build order — most mechanical piece (§16).

Current status: minimal but functional cover page via reportlab. TODO items
are the real scope:
  TODO(bank-pack): merge the uploaded source documents into the pack
  TODO(bank-pack): per-bank checklist templates (bank acceptance differs by AD, §9)
  TODO(bank-pack): Form 145/146 data annexure in the layout banks expect
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.models.case import Case


def generate_bank_pack_pdf(case: Case) -> bytes:
    """Render a one-page remittance summary PDF for a certified/filed case."""
    if case.status not in ("certified", "filed"):
        raise ValueError("bank pack is only generated for certified or filed cases")

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    _, height = A4

    y = height - 30 * mm
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(25 * mm, y, "Remittance Compliance Pack — Form 145/146")
    y -= 8 * mm
    pdf.setFont("Helvetica", 9)
    pdf.drawString(25 * mm, y, "Prepared by Suntech Business Solutions platform — workflow support only.")
    y -= 12 * mm

    rows = [
        ("Case ID", str(case.id)),
        ("Status", case.status),
        ("Amount", f"{case.amount} {case.currency or ''}".strip()),
        ("RBI purpose code", case.purpose_code or "—"),
        ("Part classification", case.part_classification or "—"),
        ("UDIN", case.udin or "—"),
        ("DSC reference", case.dsc_reference or "—"),
        ("Certified at", str(case.certified_at) if case.certified_at else "—"),
        ("Generated", datetime.now(timezone.utc).isoformat(timespec="seconds")),
    ]
    pdf.setFont("Helvetica", 11)
    for label, value in rows:
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(25 * mm, y, f"{label}:")
        pdf.setFont("Helvetica", 11)
        pdf.drawString(75 * mm, y, value)
        y -= 8 * mm

    y -= 6 * mm
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(
        25 * mm,
        y,
        "Bank acceptance depends on the authorised dealer. This pack supports, "
        "not replaces, the AD's own checks.",
    )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
