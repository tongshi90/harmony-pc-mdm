"""成员分组（部门）· 人员核心表."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SysDepartment(Base):
    """成员分组 / 部门 t_sys_department.

    parent_id 为空表示顶级机构；initial_policy_id 为空表示不绑定初始策略。
    """

    __tablename__ = "t_sys_department"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 绑定 t_initial_policy.id；空 = 不套用初始策略
    initial_policy_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 0禁用 1启用
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SysMember(Base):
    """企业成员 t_sys_member（核心：姓名 / 工号 / 账号 / 密码 / 分组）.

    账号密码为临时方案（bcrypt 存储），后续对接企业账号体系做绑定认证。
    """

    __tablename__ = "t_sys_member"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    department_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    employee_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    account: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # bcrypt 哈希；明文不落库
    password: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 0禁用 1启用
    is_delete: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
