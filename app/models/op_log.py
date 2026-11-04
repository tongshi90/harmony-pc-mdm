from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SysOpLog(Base):
    """操作审计日志 t_sys_op_log."""

    __tablename__ = "t_sys_op_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    module: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str | None] = mapped_column(String(128), nullable=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    query_params: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)  # 1成功 0失败
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
