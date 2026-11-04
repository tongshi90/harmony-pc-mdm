from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InitialPolicyItemIn(BaseModel):
    policy_code: str = Field(..., min_length=1, max_length=64)
    param: dict[str, Any] = Field(default_factory=dict)
    sort: int = Field(0, ge=0, description="配置顺序，越小越靠前")


class InitialPolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    items: list[InitialPolicyItemIn] = Field(default_factory=list)


class InitialPolicyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None
    items: list[InitialPolicyItemIn] | None = None
