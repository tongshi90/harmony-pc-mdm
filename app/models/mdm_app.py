from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MdmAppVersion(Base):
    """MDM Agent 版本表 t_mdm_app_version（仅版本仓库，无独立应用信息表）."""

    __tablename__ = "t_mdm_app_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version_name: Mapped[str] = mapped_column(String(64), nullable=False)
    version_code: Mapped[str] = mapped_column(String(20), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_md5: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 0草稿 2已发布 3已下架
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    publish_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
