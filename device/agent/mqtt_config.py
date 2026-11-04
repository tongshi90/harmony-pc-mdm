"""读取 MQTT 连接参数：优先云侧主库（只读），否则读模拟库."""

from __future__ import annotations

import sqlite3
from typing import Any

from device.config import CLOUD_DB_PATH, DEVICE_DB_PATH


def _read_mqtt_row(db_path) -> dict[str, Any] | None:
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        try:
            conn = sqlite3.connect(str(db_path))
        except sqlite3.Error:
            return None
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT host, port, tls, username, password, client_id_prefix, "
            "keep_alive, clean_session, qos FROM t_sys_mqtt_config LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return None
        host = (row["host"] or "").strip()
        if not host:
            return None
        return {
            "host": host,
            "port": int(row["port"] or 1883),
            "tls": bool(int(row["tls"] or 0)),
            "username": (row["username"] or "").strip() or None,
            "password": row["password"] or None,
            "client_id_prefix": (row["client_id_prefix"] or "mdm-sim-").strip()
            or "mdm-sim-",
            "keep_alive": int(row["keep_alive"] or 60),
            "clean_session": bool(
                int(row["clean_session"] if row["clean_session"] is not None else 1)
            ),
            "qos": int(row["qos"] or 1),
            "source": str(db_path),
        }
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def load_mqtt_config() -> dict[str, Any]:
    """主流程配置优先（云侧 mdm.db 只读），否则 device.db."""
    for path in (CLOUD_DB_PATH, DEVICE_DB_PATH):
        cfg = _read_mqtt_row(path)
        if cfg:
            return cfg
    raise RuntimeError(
        "未找到可用 MQTT 配置：请先在云侧平台基础管理填写 Broker，"
        "或执行 device/db_device_init.py --demo 写入模拟库"
    )
