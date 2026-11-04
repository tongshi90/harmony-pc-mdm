"""设备管理台请求模型."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DeviceCreateIn(BaseModel):
    """预登记单台设备（仅 SN）."""

    sn: str = Field(..., min_length=1, max_length=64, description="设备序列号")


class DeviceBatchCreateIn(BaseModel):
    """批量预登记（仅 SN 列表）."""

    sns: list[str] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="设备 SN 列表，最多 500 条",
    )
