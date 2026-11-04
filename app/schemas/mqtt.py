from __future__ import annotations

from pydantic import BaseModel, Field


class MqttConfigUpdate(BaseModel):
    """平台侧仅可配置 Broker 地址、端口与认证；其余字段用库内默认值."""

    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    username: str | None = Field(None, max_length=128)
    password: str | None = Field(
        None, max_length=255, description="传空或不传表示不修改密码"
    )
