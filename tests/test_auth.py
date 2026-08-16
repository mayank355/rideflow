import time
import pytest
from jose import jwt, JWTError

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    SECRET_KEY,
    ALGORITHM,
)


class TestPasswordHashing:
    def test_hash_is_not_the_plain_password(self):
        """The most basic security invariant — the stored value must
        never equal the original input."""
        hashed = hash_password("mypassword123")
        assert hashed != "mypassword123"

    def test_correct_password_verifies(self):
        hashed = hash_password("mypassword123")
        assert verify_password("mypassword123", hashed) is True

    def test_wrong_password_fails_verification(self):
        hashed = hash_password("mypassword123")
        assert verify_password("wrongpassword", hashed) is False

    def test_same_password_produces_different_hashes(self):
        """bcrypt includes a random salt per hash — hashing the same
        password twice must NOT produce identical output, otherwise two
        users with the same password would have identical hashes,
        leaking information (and defeating the point of salting)."""
        hash1 = hash_password("samepassword")
        hash2 = hash_password("samepassword")
        assert hash1 != hash2
        # but both still verify correctly against the original password
        assert verify_password("samepassword", hash1) is True
        assert verify_password("samepassword", hash2) is True


class TestJWTTokens:
    def test_token_roundtrip_preserves_subject_and_role(self):
        """Create a token, decode it, confirm the exact data put in
        comes back out unchanged — the core correctness guarantee of
        the whole auth system."""
        token = create_access_token(subject="driver-uuid-123", role="driver")
        payload = decode_access_token(token)

        assert payload["sub"] == "driver-uuid-123"
        assert payload["role"] == "driver"

    def test_rider_role_preserved(self):
        token = create_access_token(subject="rider-uuid-456", role="rider")
        payload = decode_access_token(token)
        assert payload["role"] == "rider"

    def test_tampered_token_fails_to_decode(self):
        """If even one character of a valid token is altered, the
        signature check must reject it — this is what actually prevents
        forged tokens, not just 'the format looks right.'"""
        token = create_access_token(subject="driver-uuid-123", role="driver")
        tampered = token[:-5] + "XXXXX"

        with pytest.raises(JWTError):
            decode_access_token(tampered)

    def test_token_signed_with_wrong_secret_is_rejected(self):
        """Simulates an attacker who knows the payload structure but
        not the actual secret key — confirms the signature check is
        doing real cryptographic work, not just checking format."""
        forged_token = jwt.encode(
            {"sub": "attacker-id", "role": "driver"},
            "wrong-secret-key",
            algorithm=ALGORITHM,
        )
        with pytest.raises(JWTError):
            decode_access_token(forged_token)

    def test_expired_token_is_rejected(self):
        """Manually construct a token with an expiry in the past,
        signed with the REAL secret — confirms expiry is actually
        enforced, not just present in the payload as unused metadata."""
        expired_payload = {
            "sub": "driver-uuid-123",
            "role": "driver",
            "exp": int(time.time()) - 3600,  # expired 1 hour ago
        }
        expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(JWTError):
            decode_access_token(expired_token)
