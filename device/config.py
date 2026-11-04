"""设备模拟器配置（与云侧完全隔离）."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

DEVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEVICE_DIR.parent
DATA_DIR = DEVICE_DIR / "data"
WEB_DIR = DEVICE_DIR / "web"
DEVICE_DB_PATH = DATA_DIR / "device.db"
# 云侧库（只读取 MQTT 配置，不写）
CLOUD_DB_PATH = REPO_ROOT / "data" / "mdm.db"


class DeviceSettings(BaseSettings):
    """环境变量前缀 DEVICE_."""

    app_name: str = "MDM 设备模拟器"
    host: str = "0.0.0.0"
    port: int = 8081
    # 云侧 HTTP 基址（策略拉取 / 快照上报）
    cloud_base_url: str = "http://127.0.0.1:8080"
    # 拉取防抖（秒）
    pull_debounce_seconds: int = 15
    # 操作日志条数上限
    log_limit: int = 500
    database_url: str = f"sqlite:///{DEVICE_DB_PATH.as_posix()}"

    class Config:
        env_prefix = "DEVICE_"


settings = DeviceSettings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
