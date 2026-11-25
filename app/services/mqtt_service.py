from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models.mqtt import SysMqttConfig
from app.mqtt.manager import MqttConnParams, mqtt_manager
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

PASSWORD_MASK = "********"
logger = logging.getLogger("mdm.mqtt")


def _to_out(row: SysMqttConfig) -> dict:
    """平台侧只暴露可编辑字段 + 连接状态；TLS/会话/管理端不在此返回."""
    st = mqtt_manager.status()
    return {
        "id": str(row.id),
        "host": row.host or "",
        "port": row.port,
        "username": row.username or "",
        "password": PASSWORD_MASK if row.password else "",
        "has_password": bool(row.password),
        "update_time": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else None,
        "connected": bool(st.get("connected")),
        "connect_enabled": bool(st.get("enabled")),
        "last_error": st.get("last_error") or "",
    }


def ensure_config(db: Session) -> SysMqttConfig:
    row = db.query(SysMqttConfig).first()
    if row:
        return row
    # 库内其余字段用与原先一致的默认值；管理端 api_* 仅作库默认，运行时读 Settings
    # 若设置了 MDM_MQTT_HOST，首行直接带上，便于 Docker 闭环首次启动即连 Broker
    env_host = (settings.mqtt_host or "").strip()
    env_user = (settings.mqtt_username or "").strip() or None
    env_pass = (settings.mqtt_password or "").strip() or None
    row = SysMqttConfig(
        id=snowflake_id(),
        host=env_host,
        port=int(settings.mqtt_port or 1883),
        tls=0,
        username=env_user,
        password=env_pass,
        client_id_prefix="mdm-pc-",
        keep_alive=60,
        qos=1,
        clean_session=1,
        api_port=settings.mqtt_api_port,
        api_username=settings.mqtt_api_username,
        api_password=settings.mqtt_api_password,
        update_time=local_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def apply_env_mqtt_defaults(db: Session) -> SysMqttConfig:
    """库内 host 为空且配置了 MDM_MQTT_HOST 时补写，不覆盖已人工配置的地址."""
    row = ensure_config(db)
    env_host = (settings.mqtt_host or "").strip()
    if not env_host or (row.host or "").strip():
        return row
    row.host = env_host
    row.port = int(settings.mqtt_port or 1883)
    env_user = (settings.mqtt_username or "").strip()
    env_pass = (settings.mqtt_password or "").strip()
    if env_user:
        row.username = env_user
    if env_pass:
        row.password = env_pass
    row.update_time = local_now()
    db.commit()
    db.refresh(row)
    logger.info("已用 MDM_MQTT_HOST=%s 种子写入 MQTT 业务配置", env_host)
    return row


def get_config(db: Session) -> dict:
    return _to_out(ensure_config(db))


def load_conn_params(db: Session) -> MqttConnParams | None:
    """从库读取可用连接参数；无 host 则返回 None."""
    row = db.query(SysMqttConfig).first()
    if not row or not (row.host or "").strip():
        return None
    return MqttConnParams(
        host=(row.host or "").strip(),
        port=int(row.port or 1883),
        tls=bool(row.tls),
        username=(row.username or "").strip() or None,
        password=row.password or None,
        client_id_prefix=(row.client_id_prefix or "mdm-").strip() or "mdm-",
        keep_alive=int(row.keep_alive or 60),
        clean_session=bool(row.clean_session if row.clean_session is not None else 1),
    )


def _resolve_password(db: Session, data) -> str | None:
    """表单密码为空或掩码时沿用库中已存密码."""
    if data.password is not None:
        pwd = (data.password or "").strip()
        if pwd and pwd != PASSWORD_MASK:
            return pwd
    row = db.query(SysMqttConfig).first()
    return (row.password if row else None) or None


def build_params_from_body(db: Session, data) -> MqttConnParams:
    """平台只提交地址/端口/认证；TLS、会话等沿用库内默认值."""
    row = db.query(SysMqttConfig).first()
    return MqttConnParams(
        host=(data.host or "").strip(),
        port=int(data.port),
        tls=bool(row.tls) if row else False,
        username=(data.username or "").strip() or None,
        password=_resolve_password(db, data),
        client_id_prefix=(
            ((row.client_id_prefix if row else None) or "mdm-pc-").strip() or "mdm-pc-"
        ),
        keep_alive=int((row.keep_alive if row else None) or 60),
        clean_session=bool(
            row.clean_session if row and row.clean_session is not None else 1
        ),
    )


def test_config(db: Session, data) -> dict:
    """探测表单配置能否连上 Broker（不落库、不切换长连接）."""
    params = build_params_from_body(db, data)
    ok, message = mqtt_manager.test_connect(params)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message}


def update_config(db: Session, data) -> dict:
    """先探测连接成功，再落库，并切换后台长连接.

    仅更新 host / port / username / password；其余列保持库内默认值不动。
    """
    params = build_params_from_body(db, data)
    ok, message = mqtt_manager.test_connect(params)
    if not ok:
        raise HTTPException(status_code=400, detail=f"连接失败，未保存：{message}")

    row = ensure_config(db)
    row.host = params.host
    row.port = params.port
    row.username = params.username
    if data.password is not None:
        pwd = (data.password or "").strip()
        if pwd and pwd != PASSWORD_MASK:
            row.password = pwd
    row.update_time = local_now()
    db.commit()
    db.refresh(row)

    try:
        mqtt_manager.apply(params)
    except Exception:  # noqa: BLE001
        logger.exception("保存后切换 MQTT 长连接失败（后台将重试）")
    return _to_out(row)


def startup_connect(db: Session) -> None:
    """服务启动时：有有效 MQTT 配置则后台连接；失败只记日志."""
    try:
        apply_env_mqtt_defaults(db)
        params = load_conn_params(db)
        mqtt_manager.start_background(params)
    except Exception:  # noqa: BLE001
        logger.exception("启动时调度 MQTT 连接失败（已忽略）")


def publish_message(sn: str, message: str = "", qos: int | None = None) -> dict:
    """经当前 MQTT 长连接向 ``mdm/{SN}/release`` 发布消息.

    qos 不传时默认 1（至少一次）。
    """
    from app.mqtt import publish_mqtt

    try:
        return publish_mqtt(sn=sn, message=message, qos=qos)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
