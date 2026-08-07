"""Pluggable OCR / document-extraction providers.

CLAUDE.md §2: extraction is an external document-AI API call, not built
in-house. The provider is selected by OCR_PROVIDER:

  * "stub"     — deterministic offline extractor for dev/tests. Returns a
                 plausible payload with a confidence score derived from the
                 file bytes, so pipeline behaviour is reproducible.
  * "external" — calls OCR_API_URL with OCR_API_KEY. Wire the real vendor here
                 (Azure Document Intelligence, Google DocAI, Textract, or an
                 Indian document-AI vendor) — one class, one method.

Both return an ExtractionResult; the pipeline does not care which ran.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ExtractionResult:
    confidence: float                       # 0.0 – 1.0
    fields: dict = field(default_factory=dict)
    raw_provider_payload: dict = field(default_factory=dict)


class StubOCRProvider:
    """Deterministic offline extractor. Same bytes in -> same result out."""

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        digest = hashlib.sha256(file_bytes).hexdigest()
        # Derive a stable pseudo-confidence in [0.82, 0.99] from the hash so
        # some documents land under review thresholds in demos.
        confidence = 0.82 + (int(digest[:4], 16) % 1800) / 10000
        return ExtractionResult(
            confidence=round(confidence, 3),
            fields={
                "invoice_number": f"INV-{digest[:8].upper()}",
                "detected_filename": filename,
                "sha256": digest,
            },
            raw_provider_payload={"provider": "stub"},
        )


class ExternalOCRProvider:
    """Thin client for a real document-AI API. Endpoint contract:
    POST {OCR_API_URL} with the file; JSON response with confidence + fields."""

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        if not settings.ocr_api_url:
            raise RuntimeError("OCR_PROVIDER=external but OCR_API_URL is not set")
        response = httpx.post(
            settings.ocr_api_url,
            files={"file": (filename, file_bytes)},
            headers={"Authorization": f"Bearer {settings.ocr_api_key}"},
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        return ExtractionResult(
            confidence=float(payload.get("confidence", 0.0)),
            fields=payload.get("fields", {}),
            raw_provider_payload=payload,
        )


def get_ocr_provider():
    if settings.ocr_provider == "external":
        return ExternalOCRProvider()
    return StubOCRProvider()
