from __future__ import annotations

from pydantic import BaseModel, Field


class OpLogListItem(BaseModel):
    id: str
    create_time: str
    username: str = ""
    user_name: str = ""
    module: str = ""
    action: str = ""
    method: str = ""
    path: str = ""
    success: int = 0
    response_message: str = ""
    client_ip: str = ""
    duration_ms: int | None = None


class OpLogDetail(OpLogListItem):
    user_id: str | None = None
    query_params: str | None = None
    request_body: str | None = None
    response_code: int | None = None
    response_body: str | None = None
    user_agent: str | None = None


class OpLogQuery(BaseModel):
    keyword: str | None = None
    success: int | None = Field(None, description="1成功 0失败，不传则全部")
    page: int = Field(1, ge=1)
    page_size: int = Field(10, ge=1, le=100)
