"""
Tests for the PR-08 report system.

Coverage:
  - ReportService: valid submission, self-report guard, missing target,
    invalid reason code, details sanitisation.
  - POST /report endpoint: auth required, happy path, bad reason code.
  - GET /admin/reports: disabled without ADMIN_TOKEN, auth required,
    list / filter / get / status update.
"""

import uuid

import pytest

from app.models.db import ReportReasonCode, ReportStatus
from app.services.report_service import ReportError, submit_report

# ===========================================================================
# Helpers
# ===========================================================================


def _register_and_get_token(client, email: str = None, nickname: str = None) -> tuple[str, str]:
    """Register a user, return (access_token, user_id)."""
    email = email or f"u{uuid.uuid4().hex[:8]}@test.com"
    nickname = nickname or f"P{uuid.uuid4().hex[:5]}"
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": "Test1234!", "nickname": nickname},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    # Fetch user_id via /me/profile
    profile = client.get("/me/profile", headers={"Authorization": f"Bearer {token}"})
    user_id = profile.json()["user_id"]
    return token, user_id


# ===========================================================================
# TestReportService — unit tests (no HTTP)
# ===========================================================================


class TestReportService:
    def test_valid_submission(self, db):
        report = submit_report(
            db,
            reporter_user_id="reporter-1",
            reported_user_id="reported-1",
            reported_connection_id=None,
            reason_code="emote_spam",
            details="Too many fire emotes",
            room_code="ABCD12",
            match_id=None,
        )
        assert report.id is not None
        assert report.reason_code == ReportReasonCode.EMOTE_SPAM
        assert report.status == ReportStatus.OPEN
        assert report.details == "Too many fire emotes"

    def test_missing_target_raises(self, db):
        with pytest.raises(ReportError, match="필수"):
            submit_report(
                db,
                reporter_user_id="r1",
                reported_user_id=None,
                reported_connection_id=None,
                reason_code="cheating",
                details=None,
                room_code=None,
                match_id=None,
            )

    def test_self_report_raises(self, db):
        with pytest.raises(ReportError, match="자기 자신"):
            submit_report(
                db,
                reporter_user_id="same-user",
                reported_user_id="same-user",
                reported_connection_id=None,
                reason_code="other",
                details=None,
                room_code=None,
                match_id=None,
            )

    def test_invalid_reason_code_raises(self, db):
        with pytest.raises(ReportError, match="유효하지 않은"):
            submit_report(
                db,
                reporter_user_id="r1",
                reported_user_id="r2",
                reported_connection_id=None,
                reason_code="totally_made_up",
                details=None,
                room_code=None,
                match_id=None,
            )

    def test_details_trimmed_to_280(self, db):
        long_details = "x" * 400
        report = submit_report(
            db,
            reporter_user_id=None,
            reported_user_id=None,
            reported_connection_id="conn-abc",
            reason_code="other",
            details=long_details,
            room_code=None,
            match_id=None,
        )
        assert len(report.details) == 280

    def test_connection_id_only_accepted(self, db):
        """Reporter can target by connection_id alone (guest vs guest)."""
        report = submit_report(
            db,
            reporter_user_id=None,
            reported_user_id=None,
            reported_connection_id="conn-xyz",
            reason_code="abusive_language",
            details=None,
            room_code=None,
            match_id=None,
        )
        assert report.reported_connection_id == "conn-xyz"

    def test_empty_details_stored_as_none(self, db):
        report = submit_report(
            db,
            reporter_user_id="r1",
            reported_user_id="r2",
            reported_connection_id=None,
            reason_code="other",
            details="   ",  # whitespace-only → None
            room_code=None,
            match_id=None,
        )
        assert report.details is None

    def test_duplicate_report_returns_existing(self, db):
        """Submitting same (reporter, reported, reason, match) twice returns first."""
        first = submit_report(
            db,
            reporter_user_id="reporter-dup",
            reported_user_id="reported-dup",
            reported_connection_id=None,
            reason_code="emote_spam",
            details="first report",
            room_code="ROOM01",
            match_id="match-abc",
        )
        second = submit_report(
            db,
            reporter_user_id="reporter-dup",
            reported_user_id="reported-dup",
            reported_connection_id=None,
            reason_code="emote_spam",
            details="duplicate report",
            room_code="ROOM01",
            match_id="match-abc",
        )
        assert second.id == first.id

    def test_different_reason_creates_new_report(self, db):
        first = submit_report(
            db,
            reporter_user_id="reporter-x",
            reported_user_id="reported-x",
            reported_connection_id=None,
            reason_code="emote_spam",
            details=None,
            room_code=None,
            match_id="match-xyz",
        )
        second = submit_report(
            db,
            reporter_user_id="reporter-x",
            reported_user_id="reported-x",
            reported_connection_id=None,
            reason_code="cheating",  # different reason
            details=None,
            room_code=None,
            match_id="match-xyz",
        )
        assert second.id != first.id


# ===========================================================================
# TestReportEndpoint — HTTP integration tests
# ===========================================================================


class TestReportEndpoint:
    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            "/report",
            json={
                "reported_connection_id": "conn-abc",
                "reason_code": "emote_spam",
            },
        )
        assert resp.status_code == 401

    def test_happy_path_returns_201(self, client):
        token, reporter_id = _register_and_get_token(client)
        _, reported_id = _register_and_get_token(client)

        resp = client.post(
            "/report",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "reported_user_id": reported_id,
                "reason_code": "emote_spam",
                "details": "Sent fire 100 times",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "report_id" in data
        assert data["status"] == "open"

    def test_invalid_reason_returns_400(self, client):
        token, _ = _register_and_get_token(client)
        resp = client.post(
            "/report",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "reported_connection_id": "conn-abc",
                "reason_code": "nonsense",
            },
        )
        assert resp.status_code == 400

    def test_missing_target_returns_400(self, client):
        token, _ = _register_and_get_token(client)
        resp = client.post(
            "/report",
            headers={"Authorization": f"Bearer {token}"},
            json={"reason_code": "cheating"},
        )
        assert resp.status_code == 400

    def test_self_report_returns_400(self, client):
        token, user_id = _register_and_get_token(client)
        resp = client.post(
            "/report",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "reported_user_id": user_id,
                "reason_code": "other",
            },
        )
        assert resp.status_code == 400

    @pytest.mark.parametrize(
        "reason",
        ["emote_spam", "abusive_language", "cheating", "nickname_violation", "other"],
    )
    def test_all_reason_codes_accepted(self, client, reason):
        token, _ = _register_and_get_token(client)
        resp = client.post(
            "/report",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "reported_connection_id": "conn-test",
                "reason_code": reason,
            },
        )
        assert resp.status_code == 201


# ===========================================================================
# TestAdminEndpoints — HTTP integration tests
# ===========================================================================


class TestAdminEndpoints:
    def test_list_reports_disabled_without_token(self, client):
        """Admin endpoints return 503 when ADMIN_TOKEN is not set."""
        resp = client.get(
            "/admin/reports",
            headers={"Authorization": "Bearer anything"},
        )
        assert resp.status_code == 503

    def test_list_reports_requires_admin_token(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_TOKEN", "secret-admin-token")

        resp = client.get(
            "/admin/reports",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_list_reports_returns_empty(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_TOKEN", "secret-admin-token")

        resp = client.get(
            "/admin/reports",
            headers={"Authorization": "Bearer secret-admin-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_list_reports_returns_submitted(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_TOKEN", "secret-admin-token")

        token, _ = _register_and_get_token(client)
        client.post(
            "/report",
            headers={"Authorization": f"Bearer {token}"},
            json={"reported_connection_id": "c1", "reason_code": "emote_spam"},
        )

        resp = client.get(
            "/admin/reports",
            headers={"Authorization": "Bearer secret-admin-token"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1
        assert resp.json()["items"][0]["reason_code"] == "emote_spam"

    def test_filter_by_status(self, client, monkeypatch, db):
        from app.config import settings
        from app.services.report_service import submit_report

        monkeypatch.setattr(settings, "ADMIN_TOKEN", "secret-admin-token")

        submit_report(
            db,
            reporter_user_id=None,
            reported_user_id=None,
            reported_connection_id="c1",
            reason_code="other",
            details=None,
            room_code=None,
            match_id=None,
        )

        resp = client.get(
            "/admin/reports?status=open",
            headers={"Authorization": "Bearer secret-admin-token"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(i["status"] == "open" for i in items)

        resp2 = client.get(
            "/admin/reports?status=reviewed",
            headers={"Authorization": "Bearer secret-admin-token"},
        )
        assert resp2.json()["items"] == []

    def test_get_report_by_id(self, client, monkeypatch, db):
        from app.config import settings
        from app.services.report_service import submit_report

        monkeypatch.setattr(settings, "ADMIN_TOKEN", "secret-admin-token")

        report = submit_report(
            db,
            reporter_user_id=None,
            reported_user_id=None,
            reported_connection_id="c2",
            reason_code="cheating",
            details=None,
            room_code=None,
            match_id=None,
        )

        resp = client.get(
            f"/admin/reports/{report.id}",
            headers={"Authorization": "Bearer secret-admin-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == report.id
        assert resp.json()["reason_code"] == "cheating"

    def test_update_report_status(self, client, monkeypatch, db):
        from app.config import settings
        from app.services.report_service import submit_report

        monkeypatch.setattr(settings, "ADMIN_TOKEN", "secret-admin-token")

        report = submit_report(
            db,
            reporter_user_id=None,
            reported_user_id=None,
            reported_connection_id="c3",
            reason_code="other",
            details=None,
            room_code=None,
            match_id=None,
        )

        resp = client.patch(
            f"/admin/reports/{report.id}",
            headers={"Authorization": "Bearer secret-admin-token"},
            json={"status": "reviewed"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "reviewed"

    def test_get_nonexistent_report_returns_404(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ADMIN_TOKEN", "secret-admin-token")

        resp = client.get(
            "/admin/reports/no-such-id",
            headers={"Authorization": "Bearer secret-admin-token"},
        )
        assert resp.status_code == 404

    def test_pagination_total_reflects_all_matches_not_page_size(self, client, monkeypatch, db):
        """total must be the full filtered count, not len(items) on the current page."""
        from app.config import settings
        from app.services.report_service import submit_report

        monkeypatch.setattr(settings, "ADMIN_TOKEN", "secret-admin-token")

        # Insert 5 reports.
        for i in range(5):
            submit_report(
                db,
                reporter_user_id=None,
                reported_user_id=None,
                reported_connection_id=f"conn-{i}",
                reason_code="other",
                details=None,
                room_code=None,
                match_id=None,
            )

        # Fetch only 2 per page.
        resp = client.get(
            "/admin/reports?limit=2&offset=0",
            headers={"Authorization": "Bearer secret-admin-token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2  # page has 2 items
        assert body["total"] == 5  # but total reflects all 5 rows
        assert body["limit"] == 2
        assert body["offset"] == 0
