"""业务卡片 · 企业同步：申请主表 + 审批步骤副表."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BizCard(Base):
    """申请单主表 t_biz_card（按 biz_id 整单覆盖，只存最新快照）."""

    __tablename__ = "t_biz_card"

    biz_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(String(512), nullable=False)
    # 提交人工号；语义对齐 t_sys_member.employee_id，不建强制外键
    applicant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    submit_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    overall_status: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )  # PENDING / APPROVED / REJECTED
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_step: Mapped[int] = mapped_column(Integer, nullable=False)
    current_handler_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    handle_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # REPORT=企业上报；日后 QUERY=补偿查询
    last_source: Mapped[str] = mapped_column(String(16), nullable=False, default="REPORT")


class BizCardStep(Base):
    """审批步骤副表 t_biz_card_step（整单覆盖时按 biz_id 删后重插）."""

    __tablename__ = "t_biz_card_step"
    __table_args__ = (
        UniqueConstraint("biz_id", "step", name="uq_biz_card_step_biz_step"),
        Index("ix_biz_card_step_handler_status", "handler_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    biz_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    handler_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # APPROVED / REJECTED / PENDING / WAITING
    handle_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    occur_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finish_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
