"""Initial schema: users, profiles, user_collection

Revision ID: 001
Revises:
Create Date: 2026-03-31

Creates the three core tables needed for account identity and collection
persistence. No game-state tables are created here (those come in later PRs).
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_type",
            sa.Enum("registered", "guest", name="accounttype"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), unique=True, nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "suspended", "deleted", name="userstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "profiles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("nickname", sa.String(50), nullable=False),
        sa.Column("avatar_id", sa.String(50), nullable=True),
        sa.Column("currency", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hidden_mmr", sa.Integer(), nullable=True),
        sa.Column("total_games", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_wins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("emote_loadout_json", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_table(
        "user_collection",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("soldier_id", sa.Integer(), primary_key=True),
        sa.Column(
            "unlocked_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("source", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_collection")
    op.drop_table("profiles")
    op.drop_index("ix_users_email", "users")
    op.drop_table("users")
    # Drop enum types (PostgreSQL only; SQLite ignores)
    op.execute("DROP TYPE IF EXISTS accounttype")
    op.execute("DROP TYPE IF EXISTS userstatus")
