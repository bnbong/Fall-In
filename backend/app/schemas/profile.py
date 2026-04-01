"""
Pydantic schemas for profile and collection endpoints.

Note: hidden_mmr is intentionally absent from ProfileResponse.
It is stored in the DB but never exposed to clients in the beta build.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    user_id: str
    nickname: str
    avatar_id: Optional[str]
    currency: int
    total_games: int
    total_wins: int
    account_type: str


class CollectionEntry(BaseModel):
    soldier_id: int
    unlocked_at: datetime
    source: Optional[str]


class CollectionResponse(BaseModel):
    items: list[CollectionEntry]
    total: int
