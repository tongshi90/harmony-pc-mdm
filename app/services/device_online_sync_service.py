"""设备在线状态同步：查询 EMQX 已连接 client + 更新 t_device（整体加锁）."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.device import Device
from app.utils.mqtt_clients import query_connected_clients
from app.utils.timeutil import now as local_now

logger = logging.getLogger("mdm.device.online_sync")

# 进程内互斥：定时任务与策略下发共用，避免并发双写
_sync_lock = threading.Lock()


@dataclass
class DeviceOnlineSyncResult:
    """设备在线同步结果."""

    ok: bool
    skipped: bool = False
    online_sns: list[str] = field(default_factory=list)
    online_count: int = 0
    offline_count: int = 0
    updated_count: int = 0
    synced_at: datetime | None = None
    message: str = ""


def sync_device_online_status(db: Session | None = None) -> DeviceOnlineSyncResult:
    """查询 MQTT 在线 client，并更新全部非挂失设备的在线状态.

    - 查询失败：不改库，返回 ok=False / skipped=True
    - 查询成功且 client 为空：非挂失设备全部标离线
    - status=3（挂失）不改动
    - 全程加锁，同时只允许一个同步在执行
    """
    with _sync_lock:
        return _sync_device_online_status_locked(db)


def _sync_device_online_status_locked(db: Session | None = None) -> DeviceOnlineSyncResult:
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        query = query_connected_clients(db)
        if not query.ok:
            logger.warning(
                "[设备在线同步] 查询已连接 SN 失败（未改库）: %s", query.message
            )
            return DeviceOnlineSyncResult(
                ok=False,
                skipped=True,
                message=query.message or "在线查询失败",
                synced_at=local_now(),
            )

        online_list = sorted(
            {str(x).strip() for x in query.client_ids if str(x).strip()}
        )
        online_set = set(online_list)
        ts = local_now()
        devices = db.query(Device).all()
        online_count = 0
        offline_count = 0
        updated = 0

        for device in devices:
            # 1 在线 2 离线 3 挂失 —— 挂失不自动改
            if int(device.status or 0) == 3:
                continue
            sn = (device.sn or "").strip()
            if not sn:
                continue
            if sn in online_set:
                if device.status != 1:
                    updated += 1
                device.status = 1
                device.online_time = ts
                device.update_time = ts
                online_count += 1
            else:
                if device.status != 2:
                    device.status = 2
                    device.update_time = ts
                    updated += 1
                offline_count += 1

        db.commit()
        result = DeviceOnlineSyncResult(
            ok=True,
            skipped=False,
            online_sns=sorted(online_set),
            online_count=online_count,
            offline_count=offline_count,
            updated_count=updated,
            synced_at=ts,
            message=(
                f"同步完成：在线 {online_count} · 离线 {offline_count} · "
                f"变更 {updated} · Broker 连接数 {len(online_set)}"
            ),
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("设备在线同步失败")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return DeviceOnlineSyncResult(
            ok=False,
            skipped=True,
            message=str(exc) or "同步异常",
            synced_at=local_now(),
        )
    finally:
        if own_session and db is not None:
            db.close()
