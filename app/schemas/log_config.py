from __future__ import annotations

from pydantic import BaseModel, Field


class LogConfigUpdate(BaseModel):
    retention_days: int = Field(
        ...,
        ge=1,
        le=3650,
        description="操作日志保留天数（1～3650）",
    )
