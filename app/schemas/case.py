"""Pydantic schemas for cases, documents, events, and classification."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ClientCreate(BaseModel):
    name: str
    pan: str | None = None


class ClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    pan: str | None
    created_at: datetime


class VendorCreate(BaseModel):
    client_id: uuid.UUID
    name: str
    country: str | None = None
    tin: str | None = None
    trc_valid_until: date | None = None


class VendorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    country: str | None
    tin: str | None
    trc_valid_until: date | None


class CaseCreate(BaseModel):
    """Payload to open a new case (one remittance)."""

    client_id: uuid.UUID
    vendor_id: uuid.UUID | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    purpose_code: str | None = None
    # Anchors the FY threshold window; defaults to the creation date if omitted.
    remittance_date: date | None = None


class CaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    client_id: uuid.UUID
    vendor_id: uuid.UUID | None
    status: str
    remittance_date: date | None
    amount: Decimal | None
    currency: str | None
    purpose_code: str | None
    part_classification: str | None
    rule_version_id: uuid.UUID | None
    classification_reasons: dict | None
    dsc_reference: str | None
    udin: str | None
    certified_at: datetime | None
    created_at: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    doc_type: str
    original_filename: str | None
    content_type: str | None
    confidence_score: Decimal | None
    created_at: datetime


class CaseEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    case_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    event_type: str
    old_status: str | None
    new_status: str | None
    message: str | None
    detail: dict | None
    created_at: datetime


class CertifyRequest(BaseModel):
    """CA certification payload. Entered by a human CA in the review dashboard.

    Both references are required: a case cannot be certified without recording
    the DSC reference and the UDIN (CLAUDE.md §1 — this step is never automated).
    """

    dsc_reference: str = Field(min_length=1)
    udin: str = Field(min_length=1)
    actor_user_id: uuid.UUID


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    email: str
    role: str


class DashboardStats(BaseModel):
    cases_today: int
    in_automation: int
    awaiting_ca_review: int
    filed_today: int
    by_status: dict[str, int]
