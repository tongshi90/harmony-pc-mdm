from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AppBase(Base):
    """应用基础表 t_app_base（应用仓库）."""

    __tablename__ = "t_app_base"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_name: Mapped[str] = mapped_column(String(64), nullable=False)
    app_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # 端侧协议用：AppIdentifier / Bundle Name（暂入手填，后续可从 HAP 解析）
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
