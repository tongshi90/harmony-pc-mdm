"""设备侧上报请求模型."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LocationReportIn(BaseModel):
    """设备位置上报."""

    SN: str = Field(..., min_length=1, max_length=64, description="设备 SN")
    longitude: str = Field(..., min_length=1, max_length=32, description="经度")
    latitude: str = Field(..., min_length=1, max_length=32, description="纬度")


class SnapshotAppInfoIn(BaseModel):
    """已安装应用（协议字段；appId 对应 t_app_base.app_id）."""

    appId: str = Field(..., min_length=1, max_length=128, description="业务 App ID")
    version: str = Field(..., min_length=1, max_length=64, description="安装版本名/版本号")


class SnapshotReportIn(BaseModel):
    """设备当前快照上报（策略 + 已装应用）."""

    SN: str = Field(..., min_length=1, max_length=64, description="设备 SN")
    deviceInfo: dict[str, Any] | None = Field(
        None,
        description="设备基本信息；仅当 t_device.basic_info_synced=0 时首次落库并置位，之后忽略",
    )
    appInfos: list[SnapshotAppInfoIn] | None = Field(
        None, description="已安装应用列表；缺省按空列表全量覆盖"
    )
    snapshot: list[dict[str, Any]] | None = Field(
        None, description="当前策略快照（协议 sceneCode/commandCode + param）；缺省按空列表全量覆盖"
    )
