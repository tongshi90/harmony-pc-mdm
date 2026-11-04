from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"


class Settings(BaseSettings):
    app_name: str = "企业终端管理云平台"
    debug: bool = True
    database_url: str = f"sqlite:///{(DATA_DIR / 'mdm.db').as_posix()}"
    secret_key: str = "harmony-pc-mdm-dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 12
    algorithm: str = "HS256"
    # 默认超级管理员（首次初始化写入）
    default_admin_username: str = "admin"
    default_admin_password: str = "12345678"  # 调试阶段简易密码
    default_admin_name: str = "系统管理员"
    snowflake_worker_id: int = 1
    snowflake_datacenter_id: int = 1
    # EMQX 管理端（Dashboard / 在线查询 REST API）——仅配置文件 / 启动环境变量，平台侧不可改
    # 环境变量：MDM_MQTT_API_HOST / MDM_MQTT_API_PORT / MDM_MQTT_API_USERNAME / MDM_MQTT_API_PASSWORD
    # mqtt_api_host 为空时回落业务 MQTT 的 host（t_sys_mqtt_config.host）
    mqtt_api_host: str = ""
    mqtt_api_port: int = 18083
    mqtt_api_username: str = "admin"
    mqtt_api_password: str = "Nv7Kq2Rm9Xp4Tw6B"
    # 设备在线状态全量同步周期（秒）；定时任务与策略下发共用 sync_device_online_status
    device_online_sync_interval_seconds: int = 30
    # 启动后延迟多久跑首轮同步（秒），避开与 MQTT 建连抢时机
    device_online_sync_startup_delay_seconds: int = 30
    # 设备拉取策略后，等待回执的超时（分钟）；超时仅影响展示，查询时落库为失败
    strategy_execute_timeout_minutes: int = 30
    # MDM Agent 包名（端侧 getInfo.bundleName；管理台只维护版本，包名走配置）
    # 环境变量：MDM_AGENT_BUNDLE_NAME
    agent_bundle_name: str = "com.huawei.mdm.demo"

    class Config:
        env_prefix = "MDM_"


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
