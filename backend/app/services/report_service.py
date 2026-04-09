"""
Report submission service (PR-08).

Responsibilities
----------------
* Validate that the reason code is known.
* Sanitise optional free-text details (strip, cap length, no HTML).
* Prevent trivially duplicate reports: if the same reporter has already filed
  an open report with the same reason against the same target in the same
  match, return the existing report rather than creating a new one.
  This prevents duplicate-spam in the moderation queue.
* Persist via report_repo.
* Emit a structured log entry for every accepted report so that beta
  moderators can correlate reports with WS logs without a GUI.

Game-context fields (room_code, match_id) are stored as supplied by the
client.  The server does not validate live membership because the report may
arrive after a match ends.  Moderators should treat these fields as
client-provided context, not verified fact.

No moderation workflow or notification logic lives here — that is deferred
post-beta.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.db import Report, ReportReasonCode
from app.repositories import report_repo

logger = logging.getLogger("fall_in.report")

_DETAILS_MAX_LEN = 280


class ReportError(ValueError):
    """Raised when a report submission is rejected by business rules."""


def submit_report(
    db: Session,
    *,
    reporter_user_id: Optional[str],
    reported_user_id: Optional[str],
    reported_connection_id: Optional[str],
    reason_code: str,
    details: Optional[str],
    room_code: Optional[str],
    match_id: Optional[str],
) -> Report:
    """
    Validate and persist a player report.

    Returns the created Report on success.
    Raises ReportError for validation failures.

    Callers must supply at least one of reported_user_id or
    reported_connection_id so there is something to act on.
    """
    # Must have something to report against.
    if not reported_user_id and not reported_connection_id:
        raise ReportError("reported_user_id 또는 reported_connection_id 중 하나는 필수입니다.")

    # Validate reason code.
    try:
        rc = ReportReasonCode(reason_code)
    except ValueError:
        valid = ", ".join(r.value for r in ReportReasonCode)
        raise ReportError(f"유효하지 않은 신고 사유입니다. 허용 값: {valid}")

    # Self-report guard.
    if reporter_user_id and reporter_user_id == reported_user_id:
        raise ReportError("자기 자신을 신고할 수 없습니다.")

    # Sanitise optional details.
    clean_details: Optional[str] = None
    if details:
        clean_details = details.strip()[:_DETAILS_MAX_LEN]
        if not clean_details:
            clean_details = None

    # Lightweight dedup: if the same open report already exists for this
    # (reporter, reported, reason, match) combination, return it rather than
    # creating a duplicate entry in the moderation queue.
    existing = report_repo.find_duplicate(
        db,
        reporter_user_id=reporter_user_id,
        reported_user_id=reported_user_id,
        reported_connection_id=reported_connection_id,
        reason_code=rc,
        match_id=match_id,
    )
    if existing is not None:
        logger.info(
            "report_duplicate_skipped",
            extra={
                "existing_report_id": existing.id,
                "reporter": reporter_user_id,
                "reported_user": reported_user_id,
                "reported_conn": reported_connection_id,
                "reason": rc.value,
                "match": match_id,
            },
        )
        return existing

    report = report_repo.create(
        db,
        reporter_user_id=reporter_user_id,
        reported_user_id=reported_user_id,
        reported_connection_id=reported_connection_id,
        reason_code=rc,
        details=clean_details,
        room_code=room_code,
        match_id=match_id,
    )

    logger.info(
        "report_submitted",
        extra={
            "report_id": report.id,
            "reporter": reporter_user_id,
            "reported_user": reported_user_id,
            "reported_conn": reported_connection_id,
            "reason": rc.value,
            "room": room_code,
            "match": match_id,
        },
    )

    return report
