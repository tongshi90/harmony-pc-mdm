from __future__ import annotations

from pydantic import BaseModel, Field


class RoleCreate(BaseModel):
    role_name: str = Field(..., min_length=1, max_length=64)
    role_code: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    status: int = Field(1, ge=0, le=1)
    menu_codes: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    role_name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = None
    status: int | None = Field(None, ge=0, le=1)
    menu_codes: list[str] | None = None


class RoleStatusUpdate(BaseModel):
    status: int = Field(..., ge=0, le=1)
