"""成员分组请求模型."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    parent_id: int | None = Field(None, description="上级分组；空=顶级机构")
    initial_policy_id: int | None = Field(
        None, description="初始策略模板；空=不绑定（设备绑定不套用初始策略）"
    )
    description: str | None = None
    status: int = Field(1, ge=0, le=1)


class DepartmentUpdate(BaseModel):
    """编辑可改名称/策略/说明/状态；上级分组不可改（即使传入 parent_id 也忽略）."""

    name: str = Field(..., min_length=1, max_length=64)
    parent_id: int | None = Field(
        None, description="兼容旧前端；服务端忽略，不允许修改上级"
    )
    initial_policy_id: int | None = Field(
        None, description="初始策略模板；空=不绑定（设备绑定不套用初始策略）"
    )
    description: str | None = None
    status: int = Field(1, ge=0, le=1)
