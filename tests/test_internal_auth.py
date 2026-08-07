"""Internal pipeline endpoint auth — the shared-secret gate n8n calls through."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes.internal import verify_internal_token
from app.core.config import settings


class TestInternalToken:
    def test_correct_token_passes(self):
        verify_internal_token(settings.internal_api_token)

    def test_wrong_token_rejected(self):
        with pytest.raises(HTTPException) as exc:
            verify_internal_token("not-the-token")
        assert exc.value.status_code == 401

    def test_empty_token_rejected(self):
        with pytest.raises(HTTPException):
            verify_internal_token("")
