"""策略下发请求/响应模型."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PolicyDispatchItemIn(BaseModel):
    policy_code: str = Field(..., min_length=1, max_length=64)
    param: dict[str, Any] = Field(default_factory=dict)
    sort: int = Field(0, ge=0, description="配置顺序，越小越靠前")


class PolicyTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    policy_level: Literal["normal", "urgent"] = "normal"
    wait_hours: int | None = Field(
        None,
        description="普通策略最多等待小时；紧急策略忽略",
    )
    target_type: Literal["group", "member"]
    group_ids: list[str] = Field(default_factory=list)
    member_ids: list[str] = Field(default_factory=list)
    items: list[PolicyDispatchItemIn] = Field(default_factory=list)
