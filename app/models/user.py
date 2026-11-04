from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """账号表 t_user（字段对齐云侧开发文档，补充 role_id 绑定角色）."""

    __tablename__ = "t_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(64), nullable=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 0禁用 1启用
    is_delete: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0否 1是
    is_admin: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 是否系统管理员
    role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)


class UserToken(Base):
    """登录令牌表 t_user_tokens."""

    __tablename__ = "t_user_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    login_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
