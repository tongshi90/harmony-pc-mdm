from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SysLogConfig(Base):
    """系统日志配置（单行）：操作日志保留天数等."""

    __tablename__ = "t_sys_log_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 操作日志（t_sys_op_log）保留天数；定时任务按此清理
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
