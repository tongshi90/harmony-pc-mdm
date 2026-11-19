from __future__ import annotations

from pydantic import BaseModel, Field


class MdmAppVersionCreate(BaseModel):
    version_name: str = Field(..., min_length=1, max_length=64)
    version_code: str = Field(..., min_length=1, max_length=20)
    status: int = Field(0, ge=0, le=3)


class MdmAppVersionUpdate(BaseModel):
    version_name: str | None = Field(None, min_length=1, max_length=64)
    version_code: str | None = Field(None, min_length=1, max_length=20)
    status: int | None = Field(None, ge=0, le=3)


class MdmBatchUpgradeIn(BaseModel):
    """MDM Agent 批量升级：按分组写入设备预期版本并发 MQTT 通知."""

    group_ids: list[str] = Field(
        default_factory=list, description="成员分组 ID；传空且 all_groups=true 表示全部"
    )
    all_groups: bool = Field(False, description="是否选择全部分组")
