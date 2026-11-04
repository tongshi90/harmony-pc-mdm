"""设备绑定请求模型."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DeviceBindIn(BaseModel):
    SN: str = Field(..., min_length=1, max_length=64, description="设备 SN")
    userName: str = Field(..., min_length=1, max_length=64, description="成员账号")
    # 临时方案：明文传输；后续对接企业认证后按对方要求调整
    password: str = Field(..., min_length=1, max_length=256, description="成员密码（明文，临时）")
