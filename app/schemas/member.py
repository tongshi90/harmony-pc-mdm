"""人员管理请求模型."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemberCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    employee_id: str = Field(..., min_length=1, max_length=64)
    account: str = Field(..., min_length=1, max_length=64)
    # RSA-OAEP 密文，后端解密后 bcrypt 存储
    password: str = Field(..., min_length=1)
    department_id: int | str = Field(..., description="所属分组 id")
    status: int = Field(1, ge=0, le=1)


class MemberUpdate(BaseModel):
    """编辑：不可改账号/密码，可改姓名、工号、分组."""

    name: str = Field(..., min_length=1, max_length=64)
    employee_id: str = Field(..., min_length=1, max_length=64)
    department_id: int | str = Field(..., description="所属分组 id")
    status: int = Field(1, ge=0, le=1)
