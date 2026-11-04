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
