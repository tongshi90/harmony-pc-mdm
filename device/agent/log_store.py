"""操作日志（内存环，供模拟页展示）."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from device.config import settings


class LogStore:
    def __init__(self, limit: int | None = None) -> None:
        self._limit = int(limit or settings.log_limit)
        self._lock = threading.RLock()
        self._items: list[dict[str, Any]] = []

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def add(
        self,
        *,
        kind: str,
        title: str,
        detail: dict[str, Any] | None = None,
        api_path: str | None = None,
    ) -> dict[str, Any]:
        item = {
            "id": uuid.uuid4().hex,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind,
            "title": title,
            "api_path": api_path or "",
            "detail": detail or {},
        }
        with self._lock:
            self._items.insert(0, item)
            if len(self._items) > self._limit:
                self._items = self._items[: self._limit]
        return item

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._items[: max(1, min(limit, self._limit))]
            # 列表不带超大 detail，只保留摘要字段
            out = []
            for r in rows:
                out.append(
                    {
                        "id": r["id"],
                        "time": r["time"],
                        "kind": r["kind"],
                        "title": r["title"],
                        "api_path": r["api_path"],
                    }
                )
            return out

    def get(self, log_id: str) -> dict[str, Any] | None:
        with self._lock:
            for r in self._items:
                if r["id"] == log_id:
                    return dict(r)
        return None


logs = LogStore()
