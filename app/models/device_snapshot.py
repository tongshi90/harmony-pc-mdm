"""设备策略快照：预期（云侧）与当前（设备上报）."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DevicePolicyExpected(Base):
    """设备预期策略快照 t_device_policy_expected（设备 + 策略 Code 一行）."""

    __tablename__ = "t_device_policy_expected"
    __table_args__ = (
        UniqueConstraint("device_sn", "policy_code", name="uq_device_policy_expected"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_sn: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 与端云协议 commandCode / sceneCode 值一致（如 WIFI_SET、APP_MANAGEMENT）
    policy_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    param_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DevicePolicyCurrent(Base):
    """设备当前策略快照 t_device_policy_current（设备上报）."""

    __tablename__ = "t_device_policy_current"
    __table_args__ = (
        UniqueConstraint("device_sn", "policy_code", name="uq_device_policy_current"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_sn: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    param_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
