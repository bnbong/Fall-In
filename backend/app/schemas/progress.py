"""
Schemas for client progress synchronisation.

These endpoints are intentionally narrow:
  - initial merge of local single-player progress into a registered account
  - exact currency updates after in-game earn/spend events
  - idempotent soldier unlock writes
"""

from pydantic import BaseModel, Field


class ProgressMergeRequest(BaseModel):
    currency: int = Field(ge=0)
    collected_soldier_ids: list[int] = Field(default_factory=list)


class ProgressMergeResponse(BaseModel):
    currency: int
    collected_soldier_ids: list[int]
    total_collected: int


class CurrencyUpdateRequest(BaseModel):
    currency: int = Field(ge=0)


class CurrencyUpdateResponse(BaseModel):
    currency: int


class CollectionUnlockRequest(BaseModel):
    soldier_id: int = Field(ge=1)


class CollectionUnlockResponse(BaseModel):
    soldier_id: int
    added: bool
    total_collected: int
