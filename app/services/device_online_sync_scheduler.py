"""设备在线状态定时同步（后台线程）."""

from __future__ import annotations

import logging
import threading

from app.config import settings
from app.services.device_control_service import flush_pending_disk_erasures
from app.services.device_online_sync_service import sync_device_online_status
from app.services.policy_dispatch_service import flush_pending_policy_notifies

logger = logging.getLogger("mdm.device.online_sync.scheduler")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _loop() -> None:
    delay = max(0, int(settings.device_online_sync_startup_delay_seconds))
    interval = max(30, int(settings.device_online_sync_interval_seconds))
    if delay > 0 and _stop_event.wait(delay):
        return

    while not _stop_event.is_set():
        try:
            result = sync_device_online_status()
            if result.ok:
                # 上线设备：补发「待通知」策略 MQTT
                try:
                    flush_pending_policy_notifies(result.online_sns)
                except Exception:  # noqa: BLE001
                    logger.exception("上线补发策略通知异常")
                # 上线设备：补发缓存的数据擦除指令
                try:
                    flush_pending_disk_erasures(result.online_sns)
                except Exception:  # noqa: BLE001
                    logger.exception("上线补发数据擦除异常")
            else:
                logger.warning("[设备在线同步] 本轮跳过: %s", result.message)
        except Exception:  # noqa: BLE001
            logger.exception("[设备在线同步] 本轮异常")
        if _stop_event.wait(interval):
            break


def start_device_online_sync_scheduler() -> None:
    """启动后台定时同步（幂等）."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(
        target=_loop,
        name="device-online-sync",
        daemon=True,
    )
    _thread.start()


def stop_device_online_sync_scheduler() -> None:
    """请求停止后台定时同步."""
    global _thread
    _stop_event.set()
    t = _thread
    if t is not None and t.is_alive():
        t.join(timeout=5)
    _thread = None
