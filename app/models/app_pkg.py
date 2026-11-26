from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AppBase(Base):
    """应用基础表 t_app_base（应用仓库）."""

    __tablename__ = "t_app_base"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_name: Mapped[str] = mapped_column(String(64), nullable=False)
    app_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # 端侧协议：App ID 由云侧创建时自动生成；Bundle Name 创建时填写，不可改
    app_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)
    bundle_name: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)
    app_icon: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 0下架 1上架
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AppVersion(Base):
    """应用版本表 t_app_version."""

    __tablename__ = "t_app_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    version_name: Mapped[str] = mapped_column(String(64), nullable=False)
    version_code: Mapped[str] = mapped_column(String(20), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # 本地相对路径
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_md5: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0草稿 1待测试 2已发布 3已下架
    publish_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AppProfile(Base):
    """应用 Profile 表 t_app_profile（对齐商店调试 Profile；关联 t_app_base + t_store_cert）."""

    __tablename__ = "t_app_profile"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    cert_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    cert_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_delete: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
