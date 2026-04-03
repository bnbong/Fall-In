"""
SQLAlchemy ORM models.

Table layout matches the schema defined in fall_in_multiplayer_plan_v1.md §15.

Design notes:
  - UUIDs are stored as VARCHAR(36) for SQLite compatibility.
    PostgreSQL deployments can use a native UUID column type via Alembic migration
    without changing application code.
  - hidden_mmr is stored here but never exposed via the profile API.
    It is only updated by the match-result service (PR-06+).
  - UserCollection rows are keyed by (user_id, soldier_id).
    A guest user_id must never appear here — enforced at the service layer.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC for SQLite compat


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class AccountType(str, enum.Enum):
    REGISTERED = "registered"
    GUEST = "guest"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    account_type: Mapped[AccountType] = mapped_column(
        SAEnum(AccountType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    profile: Mapped["Profile"] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    collection: Mapped[list["UserCollection"]] = relationship(
        "UserCollection", back_populates="user", cascade="all, delete-orphan"
    )


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    avatar_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Never exposed via API; updated only by match-result service (PR-06+).
    hidden_mmr: Mapped[int | None] = mapped_column(Integer, nullable=True)

    total_games: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    emote_loadout_json: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    user: Mapped["User"] = relationship("User", back_populates="profile")


class UserCollection(Base):
    """
    Persistent soldier collection for registered users only.

    Invariant: guest user_ids must never appear in this table.
    The collection API enforces this via require_registered().
    """

    __tablename__ = "user_collection"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    soldier_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="collection")
