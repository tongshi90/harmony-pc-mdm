from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = ""
    data: T | None = None


class PageResult(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 12


def ok(data: Any = None, message: str = "") -> dict:
    """成功响应：message 仅失败时有值，成功默认空串."""
    return {"code": 0, "message": message or "", "data": data}


def fail(message: str, code: int = 1, data: Any = None) -> dict:
    return {"code": code, "message": message or "", "data": data}
