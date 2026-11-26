"""应用商店调试模块表（与 MDM 应用仓库 t_app_* 完全独立）."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StoreCert(Base):
    """商店证书表 t_store_cert（对齐 hmapp_cert 精简）."""

    __tablename__ = "t_store_cert"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cert_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 1=发布证书（当前仅此类型）
    cert_type: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 叶子证书 PEM（若上传 .cer/.pem 可解析则写入）
    app_cert: Mapped[str | None] = mapped_column(Text, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_delete: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StoreApp(Base):
    """商店应用表 t_store_app（对齐 hmapp_info 精简）."""

    __tablename__ = "t_store_app"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_name: Mapped[str] = mapped_column(String(128), nullable=False)
    package_name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_delete: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StoreAppVersion(Base):
    """商店应用版本表 t_store_app_version（对齐 hmapp_info_version 精简）."""

    __tablename__ = "t_store_app_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    version_name: Mapped[str] = mapped_column(String(64), nullable=False)
    version_code: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_md5: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_delete: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StoreProfile(Base):
    """商店应用 Profile 表 t_store_profile（对齐 hmapp_info_profile）。"""

    __tablename__ = "t_store_profile"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    cert_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    cert_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 1=生效
    profile_status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_delete: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
