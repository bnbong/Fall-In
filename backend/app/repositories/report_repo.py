"""
Report repository — CRUD for the reports table.

All writes go through the service layer; this module is purely data access.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.db import Report, ReportReasonCode, ReportStatus


def create(
    db: Session,
    *,
    reporter_user_id: Optional[str],
    reported_user_id: Optional[str],
    reported_connection_id: Optional[str],
    reason_code: ReportReasonCode,
    details: Optional[str],
    room_code: Optional[str],
    match_id: Optional[str],
) -> Report:
    """Persist a new report and return the committed object."""
    report = Report(
        reporter_user_id=reporter_user_id,
        reported_user_id=reported_user_id,
        reported_connection_id=reported_connection_id,
        reason_code=reason_code,
        details=details,
        room_code=room_code,
        match_id=match_id,
        status=ReportStatus.OPEN,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def get_by_id(db: Session, report_id: str) -> Optional[Report]:
    return db.get(Report, report_id)


def list_reports(
    db: Session,
    *,
    status: Optional[ReportStatus] = None,
    reason_code: Optional[ReportReasonCode] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Report]:
    """Return reports with optional filtering for admin review."""
    query = db.query(Report)
    if status is not None:
        query = query.filter(Report.status == status)
    if reason_code is not None:
        query = query.filter(Report.reason_code == reason_code)
    query = query.order_by(Report.created_at.desc())
    return query.offset(offset).limit(limit).all()


def count_reports(
    db: Session,
    *,
    status: Optional[ReportStatus] = None,
    reason_code: Optional[ReportReasonCode] = None,
) -> int:
    """Return the total number of reports matching the given filters."""
    query = db.query(Report)
    if status is not None:
        query = query.filter(Report.status == status)
    if reason_code is not None:
        query = query.filter(Report.reason_code == reason_code)
    return query.count()


def find_duplicate(
    db: Session,
    *,
    reporter_user_id: Optional[str],
    reported_user_id: Optional[str],
    reported_connection_id: Optional[str],
    reason_code: ReportReasonCode,
    match_id: Optional[str],
) -> Optional[Report]:
    """
    Return an existing open report if the same reporter has already filed
    the same reason against the same target in the same match/session.

    A duplicate is defined as: identical (reporter, reported target, reason,
    match_id) where the existing report is still OPEN.  If match_id is None
    the match is not considered (connection-ID-only reports).
    """
    query = db.query(Report).filter(
        Report.reason_code == reason_code,
        Report.status == ReportStatus.OPEN,
    )
    if reporter_user_id is not None:
        query = query.filter(Report.reporter_user_id == reporter_user_id)
    if reported_user_id is not None:
        query = query.filter(Report.reported_user_id == reported_user_id)
    elif reported_connection_id is not None:
        query = query.filter(Report.reported_connection_id == reported_connection_id)
    if match_id is not None:
        query = query.filter(Report.match_id == match_id)
    return query.first()


def update_status(db: Session, report: Report, new_status: ReportStatus) -> Report:
    report.status = new_status
    db.commit()
    db.refresh(report)
    return report
