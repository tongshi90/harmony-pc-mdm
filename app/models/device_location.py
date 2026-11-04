"""设备位置上报日志."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeviceLocationLog(Base):
    """设备位置上报日志 t_device_location_log.

    设备定时上报经纬度时追加写入；不做去重，保留轨迹历史。
    """

    __tablename__ = "t_device_location_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键（雪花 ID）")
    device_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="设备 ID → t_device.id"
    )
    device_sn: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="设备 SN"
    )
    longitude: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="经度（上报原文字符串）"
    )
    latitude: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="纬度（上报原文字符串）"
    )
    report_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True, comment="上报时间"
    )
    create_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="入库时间"
    )
