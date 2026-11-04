"""操作日志过期清理：每天凌晨 1:00 执行一次."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from app.services.log_config_service import purge_expired_op_logs

logger = logging.getLogger("mdm.op_log.purge.scheduler")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _seconds_until_next_1am(now: datetime | None = None) -> float:
    """距下一本地时间 01:00:00 的秒数."""
    now = now or datetime.now()
    target = now.replace(hour=1, minute=0, second=0, microsecond=0)
    if now >= target:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def _loop() -> None:
    while not _stop_event.is_set():
        wait_s = _seconds_until_next_1am()
        logger.info("[操作日志清理] 下次执行约 %.0f 秒后（本地 01:00）", wait_s)
        if _stop_event.wait(wait_s):
            break
        try:
            purge_expired_op_logs()
        except Exception:  # noqa: BLE001
            logger.exception("[操作日志清理] 定时任务异常")
        # 执行后若仍落在 01:00 同一分钟内，稍后再算下一天，避免同日重复跑
        if _stop_event.wait(60):
            break


def start_op_log_purge_scheduler() -> None:
    """启动后台定时清理（幂等）."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(
        target=_loop,
        name="op-log-purge",
        daemon=True,
    )
    _thread.start()


def stop_op_log_purge_scheduler() -> None:
    """请求停止后台定时清理."""
    global _thread
    _stop_event.set()
    t = _thread
    if t is not None and t.is_alive():
        t.join(timeout=5)
    _thread = None
