from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SysMqttConfig(Base):
    """MQTT 配置（单行配置表）."""

    __tablename__ = "t_sys_mqtt_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 平台侧可改：host / port / username / password
    host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=1883)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 以下列保留默认值，平台侧不可改（连接时仍读取）
    tls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0否 1是
    client_id_prefix: Mapped[str | None] = mapped_column(String(64), nullable=True)
    keep_alive: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    qos: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    clean_session: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # EMQX 管理 API：库内仅保留默认；运行时一律读 Settings（MDM_MQTT_API_*）
    api_port: Mapped[int | None] = mapped_column(Integer, nullable=True, default=18083)
    api_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    update_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
