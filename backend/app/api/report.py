"""
Report submission API (PR-08).

POST /report  — authenticated players (registered or guest) submit a report
               against another player.

The reporter is identified from the Bearer token so clients cannot spoof it.
The reported player is identified by user_id and/or connection_id from the
game context the client supplies.

Rate-limiting note: a single report per reporter+reported+reason per hour is
not enforced here — the volume for beta is low enough that manual review is
sufficient.  Add a time-based dedup query in report_repo if needed later.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.db import User
from app.services.report_service import ReportError, submit_report

router = APIRouter(prefix="/report", tags=["report"])


class ReportRequest(BaseModel):
    reported_user_id: Optional[str] = None
    reported_connection_id: Optional[str] = None
    reason_code: str
    details: Optional[str] = Field(default=None, max_length=280)
    room_code: Optional[str] = Field(default=None, max_length=10)
    match_id: Optional[str] = Field(default=None, max_length=36)


class ReportResponse(BaseModel):
    report_id: str
    status: str


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def submit(
    req: ReportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportResponse:
    """
    Submit a report against another player.

    The caller's identity is derived from the Bearer token — clients cannot
    spoof the reporter_user_id.

    Returns 400 if the reason_code is unknown or the target is missing.
    Returns 201 with the new report_id on success.
    """
    try:
        report = submit_report(
            db,
            reporter_user_id=current_user.id,
            reported_user_id=req.reported_user_id,
            reported_connection_id=req.reported_connection_id,
            reason_code=req.reason_code,
            details=req.details,
            room_code=req.room_code,
            match_id=req.match_id,
        )
    except ReportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return ReportResponse(report_id=report.id, status=report.status.value)
