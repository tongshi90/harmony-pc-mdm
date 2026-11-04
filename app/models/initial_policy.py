"""初始策略模板：模板头 + 按策略类型拆行的配置项."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InitialPolicy(Base):
    """初始策略模板 t_initial_policy."""

    __tablename__ = "t_initial_policy"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 历史字段：全局默认能力已下线，新数据固定写 0；列保留兼容旧库
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class InitialPolicyItem(Base):
    """初始策略模板项 t_initial_policy_item（每种策略类型一行）."""

    __tablename__ = "t_initial_policy_item"
    __table_args__ = (
        UniqueConstraint("policy_id", "policy_code", name="uq_initial_policy_item_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    policy_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 与策略管理 / 端云协议一致，如 WIFI_SET、APP_MANAGEMENT
    policy_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 仅 param 对象 JSON，供前端 mountCommandParamForm 回填
    param_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 列表摘要（入库，避免前端每次组装）
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 配置顺序（从小到大）
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
