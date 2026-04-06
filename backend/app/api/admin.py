"""
Minimal admin query API (PR-08).

Intentionally narrow scope: read-only access to reports for beta moderation.
No admin panel, no user management, no stats dashboards.

Authentication: static Bearer token from settings.ADMIN_TOKEN.
Set ADMIN_TOKEN to a strong random string in .env before beta deployment.
Leave it empty (default) to disable the admin endpoints entirely.

Endpoints
---------
GET /admin/reports          — list reports with optional filters
GET /admin/reports/{id}     — get a single report by ID
PATCH /admin/reports/{id}   — update report status (reviewed / dismissed)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.db import ReportReasonCode, ReportStatus
from app.repositories import report_repo

router = APIRouter(prefix="/admin", tags=["admin"])

_bearer = HTTPBearer(auto_error=False)


def _require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    """Dependency that verifies the static admin token."""
    token = settings.ADMIN_TOKEN
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin endpoints are disabled (ADMIN_TOKEN not set)",
        )
    if credentials is None or credentials.credentials != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token",
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ReportDetail(BaseModel):
    id: str
    reporter_user_id: Optional[str]
    reported_user_id: Optional[str]
    reported_connection_id: Optional[str]
    reason_code: str
    details: Optional[str]
    room_code: Optional[str]
    match_id: Optional[str]
    status: str
    created_at: str

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    items: list[ReportDetail]
    total: int
    limit: int
    offset: int


class UpdateStatusRequest(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/reports",
    response_model=ReportListResponse,
    dependencies=[Depends(_require_admin)],
)
def list_reports(
    status: Optional[str] = Query(default=None),
    reason_code: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReportListResponse:
    """
    Return a paginated list of reports.

    Optional query parameters:
      - status: open | reviewed | dismissed
      - reason_code: emote_spam | abusive_language | cheating |
                     nickname_violation | other
      - limit / offset for pagination
    """
    rs: Optional[ReportStatus] = None
    if status:
        try:
            rs = ReportStatus(status)
        except ValueError:
            valid = ", ".join(s.value for s in ReportStatus)
            raise HTTPException(400, detail=f"유효하지 않은 status. 허용 값: {valid}")

    rc: Optional[ReportReasonCode] = None
    if reason_code:
        try:
            rc = ReportReasonCode(reason_code)
        except ValueError:
            valid = ", ".join(r.value for r in ReportReasonCode)
            raise HTTPException(400, detail=f"유효하지 않은 reason_code. 허용 값: {valid}")

    # Count matching rows before applying limit/offset so `total` reflects the
    # true number of matching reports, not just the current page size.
    total = report_repo.count_reports(db, status=rs, reason_code=rc)
    reports = report_repo.list_reports(db, status=rs, reason_code=rc, limit=limit, offset=offset)
    items = [
        ReportDetail(
            id=r.id,
            reporter_user_id=r.reporter_user_id,
            reported_user_id=r.reported_user_id,
            reported_connection_id=r.reported_connection_id,
            reason_code=r.reason_code.value,
            details=r.details,
            room_code=r.room_code,
            match_id=r.match_id,
            status=r.status.value,
            created_at=r.created_at.isoformat(),
        )
        for r in reports
    ]
    return ReportListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/reports/{report_id}",
    response_model=ReportDetail,
    dependencies=[Depends(_require_admin)],
)
def get_report(report_id: str, db: Session = Depends(get_db)) -> ReportDetail:
    report = report_repo.get_by_id(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return ReportDetail(
        id=report.id,
        reporter_user_id=report.reporter_user_id,
        reported_user_id=report.reported_user_id,
        reported_connection_id=report.reported_connection_id,
        reason_code=report.reason_code.value,
        details=report.details,
        room_code=report.room_code,
        match_id=report.match_id,
        status=report.status.value,
        created_at=report.created_at.isoformat(),
    )


@router.patch(
    "/reports/{report_id}",
    response_model=ReportDetail,
    dependencies=[Depends(_require_admin)],
)
def update_report_status(
    report_id: str,
    req: UpdateStatusRequest,
    db: Session = Depends(get_db),
) -> ReportDetail:
    """Update report status to reviewed or dismissed."""
    report = report_repo.get_by_id(db, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    try:
        new_status = ReportStatus(req.status)
    except ValueError:
        valid = ", ".join(s.value for s in ReportStatus)
        raise HTTPException(400, detail=f"유효하지 않은 status. 허용 값: {valid}")

    updated = report_repo.update_status(db, report, new_status)
    return ReportDetail(
        id=updated.id,
        reporter_user_id=updated.reporter_user_id,
        reported_user_id=updated.reported_user_id,
        reported_connection_id=updated.reported_connection_id,
        reason_code=updated.reason_code.value,
        details=updated.details,
        room_code=updated.room_code,
        match_id=updated.match_id,
        status=updated.status.value,
        created_at=updated.created_at.isoformat(),
    )
