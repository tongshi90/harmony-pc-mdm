from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SysRole(Base):
    """角色表 t_sys_role（预建，本阶段前端角色页仍用静态数据）."""

    __tablename__ = "t_sys_role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 1=系统角色（不可删改禁/改权限）；0=自定义角色
    is_system: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SysRoleMenu(Base):
    """角色菜单关联表 t_sys_role_menu."""

    __tablename__ = "t_sys_role_menu"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    menu_code: Mapped[str] = mapped_column(String(64), nullable=False)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
