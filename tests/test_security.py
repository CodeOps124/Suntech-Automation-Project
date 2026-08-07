"""Password hashing and session token tests.

These run without a database. They cover the properties that matter for sign
in: a correct password verifies, a wrong one does not, hashes are salted, and
a tampered or malformed token is rejected rather than trusted.
"""

from __future__ import annotations

from app.core.security import (
    create_session_token,
    decode_session_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_correct_password_verifies(self):
        assert verify_password("suntech123", hash_password("suntech123"))

    def test_wrong_password_rejected(self):
        assert not verify_password("wrong", hash_password("suntech123"))

    def test_hash_is_not_the_plain_text(self):
        assert hash_password("suntech123") != "suntech123"

    def test_hashes_are_salted(self):
        # Same input twice must not produce the same hash.
        assert hash_password("same") != hash_password("same")

    def test_missing_hash_rejected(self):
        # A user row with no password set can never sign in.
        assert not verify_password("anything", None)
        assert not verify_password("anything", "")

    def test_malformed_hash_rejected(self):
        assert not verify_password("anything", "not-a-bcrypt-hash")

    def test_long_password_is_handled(self):
        # bcrypt caps at 72 bytes. Hash and verify must agree on the cap
        # instead of raising.
        long_pw = "a" * 200
        assert verify_password(long_pw, hash_password(long_pw))


class TestSessionToken:
    def test_round_trip_carries_identity(self):
        token = create_session_token(user_id="u1", firm_id="f1", role="ca_reviewer")
        claims = decode_session_token(token)
        assert claims is not None
        assert claims["sub"] == "u1"
        assert claims["firm_id"] == "f1"
        assert claims["role"] == "ca_reviewer"

    def test_tampered_token_rejected(self):
        token = create_session_token(user_id="u1", firm_id="f1", role="analyst")
        assert decode_session_token(token[:-3] + "abc") is None

    def test_garbage_token_rejected(self):
        assert decode_session_token("not.a.token") is None
