"""应用商店调试模块请求体."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StoreAppCreate(BaseModel):
    app_name: str = Field(..., min_length=1, max_length=128)
    package_name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None


class StoreAppUpdate(BaseModel):
    app_name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = None


class StoreProfileCreate(BaseModel):
    profile_name: str = Field(..., min_length=1, max_length=128)
    # 雪花 ID：前端以字符串提交，避免 JS 精度丢失
    cert_id: str | int
