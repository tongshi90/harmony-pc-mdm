"""策略预期变更日志：变更单头 + 策略项快照 + 目标设备/人员清单.

写入 t_device_policy_expected 的各类操作（下发 / 初始策略 / 应用批更）共用本三表。
设备是否对齐看 expected vs current，不在本表做执行状态机。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.enums.policy_change_op import DISPATCH


class PolicyTask(Base):
    """策略预期变更单 t_policy_task."""

    __tablename__ = "t_policy_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键（雪花 ID）")
    # dispatch | initial_bind | app_batch
    op_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DISPATCH,
        index=True,
        comment=(
            "变更来源：dispatch策略下发 | initial_bind初始策略(预留) | "
            "app_batch应用批量安装/卸载(装卸由策略项 param 区分)"
        ),
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="变更单名称 / 任务名称"
    )
    # 紧急度：dispatch 跟前端；app_batch 固定 normal+24h；initial_bind 固定 urgent
    policy_level: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment="策略紧急度：normal | urgent",
    )
    wait_hours: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="普通策略最多等待小时；紧急策略为空",
    )
    deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="普通策略截止时间；紧急策略为空"
    )
    # 按分组选择时写入；手动选人 / 单设备绑定等为 []
    target_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        comment="所选成员分组 ID 列表 JSON；非分组场景为 []",
    )
    target_desc: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="目标范围可读描述",
    )
    # 来源业务主键：如初始策略模板 ID、应用批更单 ID 等；dispatch 可空
    source_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="来源业务 ID（模板/批更单等）；dispatch 可空",
    )
    # 类型扩展：装卸标识以外的补充信息，JSON 文本
    ext_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="类型扩展 JSON（预留）",
    )
    creator_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="操作人管理员 ID → t_user.id"
    )
    creator_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="操作人姓名快照"
    )
    target_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="目标终端总数"
    )
    policy_summary: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="策略内容聚合摘要",
    )
    create_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="创建时间"
    )
    update_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最后更新时间"
    )


class PolicyTaskItem(Base):
    """策略预期变更项快照 t_policy_task_item."""

    __tablename__ = "t_policy_task_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键（雪花 ID）")
    task_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True, comment="所属变更单 ID → t_policy_task.id"
    )
    policy_code: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="策略指令 Code"
    )
    param_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        comment="策略参数 JSON 快照（应用批更时含安装/卸载等配置）",
    )
    summary: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="口语化摘要"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="展示顺序"
    )
    create_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="创建时间"
    )
    update_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最后更新时间"
    )


class PolicyDeviceTask(Base):
    """策略预期变更 · 目标设备与人员清单 t_policy_device_task."""

    __tablename__ = "t_policy_device_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键（雪花 ID）")
    task_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True, comment="所属变更单 ID → t_policy_task.id"
    )
    device_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True, comment="设备 ID → t_device.id"
    )
    device_sn: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="设备 SN"
    )
    member_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="绑定成员 ID → t_sys_member.id"
    )
    member_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="成员姓名快照"
    )
    employee_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="成员工号快照"
    )
    department_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="成员所属分组 ID 快照"
    )
    department_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="成员所属分组路径快照"
    )
    create_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="创建时间"
    )
    update_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="更新时间"
    )
