"""
Auth flow tests.

Covers: register, login, guest, refresh, logout, and basic token validation.
"""

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register(client: TestClient, email: str, password: str = "password123", nickname: str = "Player") -> dict:
    resp = client.post("/auth/register", json={
        "email": email,
        "password": password,
        "nickname": nickname,
    })
    return resp


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

class TestRegister:
    def test_success_returns_201_with_tokens(self, client):
        resp = _register(client, "alice@example.com", nickname="Alice")
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["account_type"] == "registered"
        assert data["token_type"] == "bearer"

    def test_duplicate_email_returns_400(self, client):
        _register(client, "dup@example.com")
        resp = _register(client, "dup@example.com")
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    def test_short_password_returns_422(self, client):
        resp = client.post("/auth/register", json={
            "email": "short@example.com",
            "password": "abc",       # < 8 chars
            "nickname": "ShortPw",
        })
        assert resp.status_code == 422

    def test_empty_nickname_returns_422(self, client):
        resp = client.post("/auth/register", json={
            "email": "nonick@example.com",
            "password": "password123",
            "nickname": "",
        })
        assert resp.status_code == 422

    def test_missing_fields_returns_422(self, client):
        resp = client.post("/auth/register", json={"email": "nopw@example.com"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_success_returns_tokens(self, client):
        _register(client, "bob@example.com", password="secure123", nickname="Bob")
        resp = client.post("/auth/login", json={
            "email": "bob@example.com",
            "password": "secure123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["account_type"] == "registered"

    def test_wrong_password_returns_401(self, client):
        _register(client, "carol@example.com", password="correct123", nickname="Carol")
        resp = client.post("/auth/login", json={
            "email": "carol@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    def test_nonexistent_email_returns_401(self, client):
        resp = client.post("/auth/login", json={
            "email": "nobody@example.com",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_wrong_password_does_not_reveal_which_part_failed(self, client):
        """Same error message for wrong password vs unknown email (timing-safe)."""
        _register(client, "dave@example.com", nickname="Dave")
        wrong_pw = client.post("/auth/login", json={"email": "dave@example.com", "password": "wrong"})
        no_user = client.post("/auth/login", json={"email": "ghost@example.com", "password": "wrong"})
        assert wrong_pw.json()["detail"] == no_user.json()["detail"]


# ---------------------------------------------------------------------------
# Guest login
# ---------------------------------------------------------------------------

class TestGuestLogin:
    def test_success_with_custom_nickname(self, client):
        resp = client.post("/auth/guest", json={"nickname": "GuestUser"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["account_type"] == "guest"
        assert data["token_type"] == "bearer"

    def test_no_refresh_token_for_guest(self, client):
        resp = client.post("/auth/guest", json={"nickname": "GuestUser"})
        data = resp.json()
        # refresh_token must be absent or explicitly null
        assert data.get("refresh_token") is None

    def test_auto_nickname_when_not_provided(self, client):
        resp = client.post("/auth/guest", json={})
        assert resp.status_code == 200
        assert resp.json()["account_type"] == "guest"

    def test_guest_token_is_valid_for_profile(self, client):
        resp = client.post("/auth/guest", json={"nickname": "ProfileGuest"})
        token = resp.json()["access_token"]
        profile = client.get("/me/profile", headers={"Authorization": f"Bearer {token}"})
        assert profile.status_code == 200
        assert profile.json()["account_type"] == "guest"


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_success_returns_new_access_token(self, client):
        reg = _register(client, "refresh@example.com", nickname="RefreshPlayer")
        refresh_token = reg.json()["refresh_token"]

        resp = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_access_token_cannot_be_used_as_refresh(self, client):
        reg = _register(client, "badrefresh@example.com", nickname="BadRefresh")
        access_token = reg.json()["access_token"]

        resp = client.post("/auth/refresh", json={"refresh_token": access_token})
        assert resp.status_code == 401

    def test_garbage_token_returns_401(self, client):
        resp = client.post("/auth/refresh", json={"refresh_token": "not.a.jwt.at.all"})
        assert resp.status_code == 401

    def test_new_access_token_is_usable(self, client):
        reg = _register(client, "newtoken@example.com", nickname="NewToken")
        refresh_token = reg.json()["refresh_token"]

        new_token = client.post("/auth/refresh", json={"refresh_token": refresh_token}).json()["access_token"]
        profile = client.get("/me/profile", headers={"Authorization": f"Bearer {new_token}"})
        assert profile.status_code == 200


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_returns_200(self, client):
        resp = client.post("/auth/logout")
        assert resp.status_code == 200

    def test_logout_response_has_detail(self, client):
        resp = client.post("/auth/logout")
        assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# Account status enforcement
# ---------------------------------------------------------------------------

class TestAccountStatus:
    """
    Suspended and deleted accounts must be blocked at every auth boundary:
    login, token-bearing HTTP requests, and WS auth.
    """

    def _suspend(self, db, email: str) -> None:
        from app.models.db import User, UserStatus
        user = db.query(User).filter(User.email == email).first()
        user.status = UserStatus.SUSPENDED
        db.commit()

    def _delete(self, db, email: str) -> None:
        from app.models.db import User, UserStatus
        user = db.query(User).filter(User.email == email).first()
        user.status = UserStatus.DELETED
        db.commit()

    def test_suspended_user_cannot_login(self, client, db):
        _register(client, "suspended@example.com", nickname="Suspended")
        self._suspend(db, "suspended@example.com")
        resp = client.post("/auth/login", json={
            "email": "suspended@example.com",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_deleted_user_cannot_login(self, client, db):
        _register(client, "deleted@example.com", nickname="Deleted")
        self._delete(db, "deleted@example.com")
        resp = client.post("/auth/login", json={
            "email": "deleted@example.com",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_suspended_user_same_error_message_as_wrong_password(self, client, db):
        """Status check must not leak more info than a wrong-password failure."""
        _register(client, "suscheck@example.com", nickname="SusCheck")
        self._suspend(db, "suscheck@example.com")
        resp_suspended = client.post("/auth/login", json={
            "email": "suscheck@example.com", "password": "password123",
        })
        resp_wrong_pw = client.post("/auth/login", json={
            "email": "suscheck@example.com", "password": "wrongpassword",
        })
        assert resp_suspended.status_code == 401
        assert resp_wrong_pw.status_code == 401
        assert resp_suspended.json()["detail"] == resp_wrong_pw.json()["detail"]

    def test_suspended_user_existing_token_rejected_on_profile(self, client, db):
        """A token issued before suspension must be rejected on subsequent requests."""
        resp = _register(client, "willsuspend@example.com", nickname="WillSuspend")
        token = resp.json()["access_token"]
        # Works before suspension
        assert client.get(
            "/me/profile", headers={"Authorization": f"Bearer {token}"}
        ).status_code == 200
        # Suspend and retry
        self._suspend(db, "willsuspend@example.com")
        assert client.get(
            "/me/profile", headers={"Authorization": f"Bearer {token}"}
        ).status_code == 401

    def test_deleted_user_existing_token_rejected_on_profile(self, client, db):
        resp = _register(client, "willdelete@example.com", nickname="WillDelete")
        token = resp.json()["access_token"]
        self._delete(db, "willdelete@example.com")
        assert client.get(
            "/me/profile", headers={"Authorization": f"Bearer {token}"}
        ).status_code == 401

    def test_suspended_user_cannot_access_collection(self, client, db):
        resp = _register(client, "sus_col@example.com", nickname="SusCol")
        token = resp.json()["access_token"]
        self._suspend(db, "sus_col@example.com")
        assert client.get(
            "/me/collection", headers={"Authorization": f"Bearer {token}"}
        ).status_code == 401
