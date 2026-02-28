"""Tests for TASK-04: JWT auth and gateway API key security."""
from datetime import timedelta

import pytest
from fastapi import HTTPException

from backend.app.core.security import (
    create_access_token,
    verify_token,
    verify_gateway_key,
    get_password_hash,
    verify_password,
)


# ── JWT round-trip ────────────────────────────────────────────────────────────

def test_create_and_verify_token():
    token = create_access_token({"sub": "user-123"})
    payload = verify_token(token)
    assert payload["sub"] == "user-123"


def test_token_contains_expiry():
    token = create_access_token({"sub": "user-456"})
    payload = verify_token(token)
    assert "exp" in payload


def test_expired_token_raises():
    token = create_access_token({"sub": "user-789"}, expires_delta=timedelta(minutes=-1))
    with pytest.raises(HTTPException) as exc_info:
        verify_token(token)
    assert exc_info.value.status_code == 401


def test_invalid_token_raises():
    with pytest.raises(HTTPException) as exc_info:
        verify_token("this.is.not.a.valid.jwt")
    assert exc_info.value.status_code == 401


def test_tampered_token_raises():
    token = create_access_token({"sub": "user-abc"})
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(HTTPException) as exc_info:
        verify_token(tampered)
    assert exc_info.value.status_code == 401


# ── Gateway API key ───────────────────────────────────────────────────────────

def test_gateway_key_valid():
    from backend.app.core.config import settings
    # Should not raise for the configured key
    verify_gateway_key(settings.GATEWAY_API_KEY)


def test_gateway_key_invalid_raises():
    with pytest.raises(HTTPException) as exc_info:
        verify_gateway_key("wrong-key-value")
    assert exc_info.value.status_code == 401


def test_gateway_key_empty_raises():
    with pytest.raises(HTTPException) as exc_info:
        verify_gateway_key("")
    assert exc_info.value.status_code == 401


# ── Password hashing ──────────────────────────────────────────────────────────

def test_password_hash_roundtrip():
    pw = "SecurePass123!"
    hashed = get_password_hash(pw)
    assert verify_password(pw, hashed) is True


def test_wrong_password_returns_false():
    hashed = get_password_hash("correct-password")
    assert verify_password("wrong-password", hashed) is False


def test_hash_is_not_plaintext():
    pw = "MyPassword"
    hashed = get_password_hash(pw)
    assert hashed != pw
