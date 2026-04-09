"""
Tests for the nickname validation service (PR-08).

Covers:
  - Valid nicknames accepted and returned stripped.
  - Empty / whitespace-only rejected.
  - Too short / too long rejected.
  - Disallowed characters rejected.
  - All-digit names rejected.
  - Reserved prefix "Guest_" rejected.
  - Banned terms rejected (case-insensitive).
  - Integration: register endpoint rejects invalid nicknames.
  - Integration: guest endpoint rejects invalid nicknames.
"""

import uuid

import pytest

from app.services.nickname_service import NicknameError, validate_nickname

# ===========================================================================
# Unit tests — validate_nickname
# ===========================================================================


class TestValidateNickname:
    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_plain_ascii_accepted(self):
        assert validate_nickname("Alice") == "Alice"

    def test_korean_accepted(self):
        assert validate_nickname("김철수") == "김철수"

    def test_mixed_korean_ascii_accepted(self):
        assert validate_nickname("Kim철수") == "Kim철수"

    def test_underscore_accepted(self):
        assert validate_nickname("sky_king") == "sky_king"

    def test_leading_trailing_whitespace_stripped(self):
        assert validate_nickname("  hello  ") == "hello"

    def test_minimum_length(self):
        assert validate_nickname("AB") == "AB"

    def test_maximum_length(self):
        assert validate_nickname("A" * 20) == "A" * 20

    def test_space_between_words_accepted(self):
        assert validate_nickname("Air Force") == "Air Force"

    # ------------------------------------------------------------------
    # Rejection cases
    # ------------------------------------------------------------------

    def test_empty_string_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("")

    def test_whitespace_only_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("   ")

    def test_too_short_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("A")

    def test_too_long_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("A" * 21)

    def test_emoji_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("cool😎")

    def test_special_chars_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("user@name")

    def test_dash_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("air-force")

    def test_all_digits_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("123456")

    def test_guest_prefix_lowercase_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("guest_abc")

    def test_guest_prefix_uppercase_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("Guest_XYZ")

    def test_banned_term_admin_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("admin")

    def test_banned_term_embedded_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("superadmin")

    def test_banned_term_case_insensitive(self):
        with pytest.raises(NicknameError):
            validate_nickname("ADMIN")

    def test_banned_korean_term_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("관리자123")

    def test_banned_korean_operator_rejected(self):
        with pytest.raises(NicknameError):
            validate_nickname("운영자")


# ===========================================================================
# Integration tests — auth endpoints enforce nickname policy
# ===========================================================================


def _unique_email():
    return f"u{uuid.uuid4().hex[:8]}@test.com"


class TestNicknameInAuthEndpoints:
    def test_register_rejects_banned_nickname(self, client):
        resp = client.post(
            "/auth/register",
            json={
                "email": _unique_email(),
                "password": "Test1234!",
                "nickname": "admin",
            },
        )
        assert resp.status_code == 422

    def test_register_rejects_emoji_nickname(self, client):
        resp = client.post(
            "/auth/register",
            json={
                "email": _unique_email(),
                "password": "Test1234!",
                "nickname": "cool😎",
            },
        )
        assert resp.status_code == 422

    def test_register_rejects_too_short_nickname(self, client):
        resp = client.post(
            "/auth/register",
            json={
                "email": _unique_email(),
                "password": "Test1234!",
                "nickname": "A",
            },
        )
        assert resp.status_code == 422

    def test_register_accepts_valid_nickname(self, client):
        resp = client.post(
            "/auth/register",
            json={
                "email": _unique_email(),
                "password": "Test1234!",
                "nickname": "SkyKing99",
            },
        )
        assert resp.status_code == 201

    def test_guest_rejects_banned_nickname(self, client):
        resp = client.post(
            "/auth/guest",
            json={"nickname": "moderator"},
        )
        assert resp.status_code == 422

    def test_guest_rejects_guest_prefix_nickname(self, client):
        resp = client.post(
            "/auth/guest",
            json={"nickname": "Guest_Impersonator"},
        )
        assert resp.status_code == 422

    def test_guest_accepts_valid_nickname(self, client):
        resp = client.post(
            "/auth/guest",
            json={"nickname": "BravePilot"},
        )
        assert resp.status_code == 200

    def test_guest_without_nickname_gets_auto_name(self, client):
        """Auto-generated Guest_ names bypass the validator (server-generated)."""
        resp = client.post("/auth/guest", json={})
        assert resp.status_code == 200
