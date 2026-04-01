"""
Profile and collection isolation tests.

Critical invariants verified:
  1. Collection is strictly keyed by user_id — no cross-user leakage.
  2. Guest accounts cannot read or write collection data.
  3. Profile is readable by both registered and guest users.
  4. Unauthenticated requests are rejected.
  5. hidden_mmr is NOT present in any profile response.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_get_token(client: TestClient, email: str, nickname: str = "Player") -> str:
    resp = client.post("/auth/register", json={
        "email": email,
        "password": "password123",
        "nickname": nickname,
    })
    assert resp.status_code == 201, resp.json()
    return resp.json()["access_token"]


def _guest_token(client: TestClient, nickname: str = "Guest") -> str:
    resp = client.post("/auth/guest", json={"nickname": nickname})
    assert resp.status_code == 200, resp.json()
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Profile endpoint
# ---------------------------------------------------------------------------

class TestProfile:
    def test_registered_user_gets_correct_profile(self, client):
        token = _register_and_get_token(client, "profile@example.com", nickname="ProfilePlayer")
        resp = client.get("/me/profile", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["nickname"] == "ProfilePlayer"
        assert data["account_type"] == "registered"
        assert data["currency"] == 0
        assert data["total_games"] == 0
        assert data["total_wins"] == 0
        assert "user_id" in data

    def test_guest_user_gets_correct_profile(self, client):
        token = _guest_token(client, nickname="GuestProfile")
        resp = client.get("/me/profile", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["nickname"] == "GuestProfile"
        assert data["account_type"] == "guest"

    def test_hidden_mmr_not_in_profile_response(self, client):
        """hidden_mmr must never be exposed via the API."""
        token = _register_and_get_token(client, "mmr@example.com", nickname="MMRPlayer")
        resp = client.get("/me/profile", headers=_auth(token))
        assert "hidden_mmr" not in resp.json()

    def test_unauthenticated_profile_rejected(self, client):
        resp = client.get("/me/profile")
        assert resp.status_code in (401, 403)  # HTTPBearer rejects missing credentials

    def test_invalid_token_profile_rejected(self, client):
        resp = client.get("/me/profile", headers={"Authorization": "Bearer totally.fake.token"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Collection endpoint — registered users
# ---------------------------------------------------------------------------

class TestCollection:
    def test_empty_collection_for_new_registered_user(self, client):
        token = _register_and_get_token(client, "empty@example.com", nickname="EmptyPlayer")
        resp = client.get("/me/collection", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_collection_contains_added_soldier(self, client, db: Session):
        """Directly insert a collection row and verify it appears via the API."""
        from app.repositories import collection_repo

        token = _register_and_get_token(client, "collector@example.com", nickname="Collector")
        profile = client.get("/me/profile", headers=_auth(token)).json()
        user_id = profile["user_id"]

        # Simulate what the match-result service will do (PR-04+)
        collection_repo.add_soldier(db, user_id, 42, source="test")

        resp = client.get("/me/collection", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["soldier_id"] == 42
        assert data["items"][0]["source"] == "test"

    def test_collection_entry_has_required_fields(self, client, db: Session):
        from app.repositories import collection_repo

        token = _register_and_get_token(client, "fields@example.com", nickname="FieldsPlayer")
        user_id = client.get("/me/profile", headers=_auth(token)).json()["user_id"]
        collection_repo.add_soldier(db, user_id, 77, source="interview")

        items = client.get("/me/collection", headers=_auth(token)).json()["items"]
        assert len(items) == 1
        item = items[0]
        assert "soldier_id" in item
        assert "unlocked_at" in item
        assert "source" in item


# ---------------------------------------------------------------------------
# Collection isolation — the critical multiplayer invariant
# ---------------------------------------------------------------------------

class TestCollectionIsolation:
    """
    Verify that user A's collection is never visible to user B.

    This directly tests the core PR-01 multiplayer invariant:
    'collection data must never cross user boundaries.'
    """

    def test_user_b_cannot_see_user_a_collection(self, client, db: Session):
        from app.repositories import collection_repo

        token_a = _register_and_get_token(client, "usera@example.com", nickname="UserA")
        token_b = _register_and_get_token(client, "userb@example.com", nickname="UserB")

        user_a_id = client.get("/me/profile", headers=_auth(token_a)).json()["user_id"]
        user_b_id = client.get("/me/profile", headers=_auth(token_b)).json()["user_id"]

        # Give user A soldier 42
        collection_repo.add_soldier(db, user_a_id, 42, source="test")

        # User A sees soldier 42
        col_a = client.get("/me/collection", headers=_auth(token_a)).json()
        assert any(item["soldier_id"] == 42 for item in col_a["items"])

        # User B sees NOTHING
        col_b = client.get("/me/collection", headers=_auth(token_b)).json()
        assert col_b["total"] == 0
        assert not any(item["soldier_id"] == 42 for item in col_b["items"])

    def test_user_ids_are_distinct(self, client):
        token_a = _register_and_get_token(client, "ida@example.com", nickname="IDA")
        token_b = _register_and_get_token(client, "idb@example.com", nickname="IDB")

        id_a = client.get("/me/profile", headers=_auth(token_a)).json()["user_id"]
        id_b = client.get("/me/profile", headers=_auth(token_b)).json()["user_id"]

        assert id_a != id_b

    def test_multiple_soldiers_isolated(self, client, db: Session):
        """User A has [42, 77]; user B has [55]; each sees only their own."""
        from app.repositories import collection_repo

        token_a = _register_and_get_token(client, "multi_a@example.com", nickname="MultiA")
        token_b = _register_and_get_token(client, "multi_b@example.com", nickname="MultiB")

        id_a = client.get("/me/profile", headers=_auth(token_a)).json()["user_id"]
        id_b = client.get("/me/profile", headers=_auth(token_b)).json()["user_id"]

        collection_repo.add_soldier(db, id_a, 42)
        collection_repo.add_soldier(db, id_a, 77)
        collection_repo.add_soldier(db, id_b, 55)

        a_ids = {item["soldier_id"] for item in client.get("/me/collection", headers=_auth(token_a)).json()["items"]}
        b_ids = {item["soldier_id"] for item in client.get("/me/collection", headers=_auth(token_b)).json()["items"]}

        assert a_ids == {42, 77}
        assert b_ids == {55}
        assert a_ids.isdisjoint(b_ids)


# ---------------------------------------------------------------------------
# Guest collection restrictions
# ---------------------------------------------------------------------------

class TestGuestCollectionRestrictions:
    def test_guest_cannot_read_collection(self, client):
        token = _guest_token(client, "GuestNoCol")
        resp = client.get("/me/collection", headers=_auth(token))
        assert resp.status_code == 403
        assert "registered" in resp.json()["detail"].lower()

    def test_guest_cannot_access_collection_even_with_valid_token(self, client):
        """A valid guest access token must still be rejected for collection access."""
        token = _guest_token(client, "ValidGuest")
        # Verify the token works for profile
        assert client.get("/me/profile", headers=_auth(token)).status_code == 200
        # But not for collection
        assert client.get("/me/collection", headers=_auth(token)).status_code == 403

    def test_unauthenticated_collection_rejected(self, client):
        resp = client.get("/me/collection")
        assert resp.status_code in (401, 403)  # HTTPBearer rejects missing credentials
