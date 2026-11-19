"""RAG 入库超时巡检（方案 D 兜底）.

仅对已写入 parse_start_time 的 parsing 文件计时；排队中的文件不计超时。
"""

from __future__ import annotations

import logging
import threading

from app.config import settings

logger = logging.getLogger("mdm.rag.ingest_watchdog")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _loop() -> None:
    interval = max(30, int(settings.rag_ingest_timeout_check_interval_seconds or 300))
    # 启动后先稍等，避免与 resume_interrupted_ingests 抢同一批行
    if _stop_event.wait(min(15, interval)):
        return
    while not _stop_event.is_set():
        try:
            from app.rag.service import fail_timed_out_ingests

            n = fail_timed_out_ingests()
            if n:
                logger.info("RAG 入库超时巡检：本轮标记失败 %s 个文件", n)
        except Exception:
            logger.exception("RAG 入库超时巡检异常")
        if _stop_event.wait(interval):
            break


def start_ingest_watchdog() -> None:
    """启动超时巡检线程（幂等）。"""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(
        target=_loop,
        name="rag-ingest-watchdog",
        daemon=True,
    )
    _thread.start()
    logger.info(
        "RAG 入库超时巡检已启动 timeout=%ss interval=%ss",
        int(settings.rag_ingest_timeout_seconds or 7200),
        max(30, int(settings.rag_ingest_timeout_check_interval_seconds or 300)),
    )


def stop_ingest_watchdog() -> None:
    """请求停止超时巡检。"""
    global _thread
    _stop_event.set()
    t = _thread
    if t is not None and t.is_alive():
        t.join(timeout=5)
    _thread = None
