from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, description="RSA 加密后的 Base64 密文")


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., description="RSA 加密后的旧密码密文")
    new_password: str = Field(..., description="RSA 加密后的新密码密文")


class LoginUserInfo(BaseModel):
    id: str
    name: str
    username: str
    phone: str | None = None
    email: str | None = None
    status: int
    is_admin: int
    role_label: str
    menus: list[str] = Field(default_factory=list)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: LoginUserInfo
