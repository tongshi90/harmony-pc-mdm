"""设备及设备已安装应用."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Device(Base):
    """设备 t_device.

    机构归属经 member_id → t_sys_member.department_id；基本信息字段供详情页展示，
    当前阶段可由种子/上报写入。
    """

    __tablename__ = "t_device"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sn: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    device_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    imei: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 绑定人员 → t_sys_member.id；空=未绑定
    member_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    # 0待激活 1已激活
    bind_status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 1在线 2离线 3已挂失
    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        comment="在线状态：1在线 | 2离线 | 3已挂失",
    )
    # 策略合规：1合规 | 0不合规（预期快照 vs 当前快照；APP_MANAGEMENT vs 已装应用）
    is_compliant: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="策略合规：1合规 | 0不合规",
    )
    # 不合规策略数量（与策略下发·终端明细「差异」一致：diffs 条数）
    policy_diff_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="不合规策略数量（差异项数）",
    )
    activate_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    online_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 基本信息是否已由快照 deviceInfo 首次同步：0未同步 | 1已同步（已同步则后续上报忽略）
    basic_info_synced: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="基本信息已同步：0否 | 1是",
    )
    # —— 详情页基本信息（种子 / 首次上报写入）——
    os: Mapped[str | None] = mapped_column(String(128), nullable=True)
    os_build: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cpu: Mapped[str | None] = mapped_column(String(128), nullable=True)
    memory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disk: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gpu: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bios_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subnet: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gateway: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dns: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mqtt_client_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 数据擦除待办：0无 · 1发送失败待补发 · 2已下发(retain)未确认，上线按库重推
    pending_disk_erasure: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeviceAppInstalled(Base):
    """设备当前已安装应用 t_device_app_installed."""

    __tablename__ = "t_device_app_installed"
    __table_args__ = (
        UniqueConstraint("device_id", "app_id", name="uq_device_app_installed"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    app_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 1指令下发 2用户安装
    install_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    install_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
