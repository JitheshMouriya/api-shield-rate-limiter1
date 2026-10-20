"""
Pydantic v2 schemas for all API request/response bodies.
"""

import math
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class ConfigureRequest(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=128)
    capacity: float = Field(..., gt=0, le=1000, description="Max tokens (1–1000)")
    refill_rate: float = Field(..., ge=0, le=100, description="Tokens/sec (0–100)")

    @field_validator("client_id")
    @classmethod
    def strip_client(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("client_id must not be blank")
        return v

    @field_validator("capacity", "refill_rate")
    @classmethod
    def must_be_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("must be a finite number")
        return v


class CheckRequest(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=128)

    @field_validator("client_id")
    @classmethod
    def strip_client(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("client_id must not be blank")
        return v


class ResetRequest(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# Response bodies
# ---------------------------------------------------------------------------

class ConfigureResponse(BaseModel):
    message: str
    client_id: str
    capacity: float
    refill_rate: float


class CheckResponse(BaseModel):
    client_id: str
    allowed: bool
    tokens_before: float
    remaining: float
    retry_after: Optional[float] = None
    capacity: float
    response_ms: Optional[float] = None


class StatusResponse(BaseModel):
    client_id: str
    tokens: float
    capacity: float
    refill_rate: float


class ResetResponse(BaseModel):
    message: str
    client_id: str


class HealthResponse(BaseModel):
    status: str
    version: str


class SummaryResponse(BaseModel):
    total: int
    allowed: int
    denied: int
    allow_pct: float


class ActivityPoint(BaseModel):
    bucket: str
    allowed: int
    denied: int


class ClientActivity(BaseModel):
    client_id: str
    total: int
    allowed: int
    denied: int


class TokenPoint(BaseModel):
    created_at: str
    tokens_before: float
    tokens_after: float
    allowed: bool


class RequestRecord(BaseModel):
    id: int
    client_id: str
    allowed: bool
    tokens_before: float
    tokens_after: float
    retry_after: Optional[float]
    response_ms: Optional[float]
    created_at: str
