"""Add reports table

Revision ID: 002
Revises: 001
Create Date: 2026-04-06

Adds the reports table for beta moderation (PR-08).
Reason codes: emote_spam, abusive_language, cheating, nickname_violation, other.
Status values: open, reviewed, dismissed.
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "reporter_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reported_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reported_connection_id", sa.String(36), nullable=True),
        sa.Column(
            "reason_code",
            sa.Enum(
                "emote_spam",
                "abusive_language",
                "cheating",
                "nickname_violation",
                "other",
                name="reportreasoncode",
            ),
            nullable=False,
        ),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("room_code", sa.String(10), nullable=True),
        sa.Column("match_id", sa.String(36), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "reviewed", "dismissed", name="reportstatus"),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_reports_reporter_user_id", "reports", ["reporter_user_id"])
    op.create_index("ix_reports_reported_user_id", "reports", ["reported_user_id"])
    op.create_index("ix_reports_status", "reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_reports_status", "reports")
    op.drop_index("ix_reports_reported_user_id", "reports")
    op.drop_index("ix_reports_reporter_user_id", "reports")
    op.drop_table("reports")
    # Drop enum types (PostgreSQL only; SQLite ignores)
    op.execute("DROP TYPE IF EXISTS reportreasoncode")
    op.execute("DROP TYPE IF EXISTS reportstatus")
