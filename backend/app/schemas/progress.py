"""
Schemas for client progress synchronisation.

These endpoints are intentionally narrow:
  - initial merge of local single-player progress into a registered account
  - delta-based reward claims with server-side validation
  - idempotent soldier unlock writes
"""

from typing import Literal

from pydantic import BaseModel, Field


class ProgressMergeRequest(BaseModel):
    currency: int = Field(ge=0)
    collected_soldier_ids: list[int] = Field(default_factory=list)


class ProgressMergeResponse(BaseModel):
    currency: int
    collected_soldier_ids: list[int]
    total_collected: int


class RewardClaimRequest(BaseModel):
    """Delta-based reward claim with reason for server validation."""

    amount: int = Field(ge=0)
    reason: Literal[
        "single_play_victory",
        "single_play_defeat",
    ]


class RewardClaimResponse(BaseModel):
    granted: int
    currency: int


class CollectionUnlockRequest(BaseModel):
    soldier_id: int = Field(ge=1)


class CollectionUnlockResponse(BaseModel):
    soldier_id: int
    added: bool
    total_collected: int
