from __future__ import annotations

from pydantic import BaseModel, Field


class AdminCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    phone: str | None = Field(None, max_length=64)
    email: str | None = Field(None, max_length=64)
    password: str = Field(..., description="RSA 加密后的初始密码密文")
    status: int = Field(1, ge=0, le=1)
    role_id: str = Field(..., description="角色 ID（必填）")


class AdminUpdate(BaseModel):
    """编辑不允许改账号、密码."""

    name: str | None = Field(None, min_length=1, max_length=64)
    phone: str | None = Field(None, max_length=64)
    email: str | None = Field(None, max_length=64)
    status: int | None = Field(None, ge=0, le=1)
    role_id: str | None = Field(None, description="角色 ID")


class AdminStatusUpdate(BaseModel):
    status: int = Field(..., ge=0, le=1)


class AdminResetPassword(BaseModel):
    password: str = Field(..., description="RSA 加密后的新密码密文")


class AdminOut(BaseModel):
    id: str
    username: str
    name: str
    phone: str | None = None
    email: str | None = None
    status: int
    is_admin: int
    role_id: str | None = None
    role_label: str
    last_login: str | None = None

    class Config:
        from_attributes = True
