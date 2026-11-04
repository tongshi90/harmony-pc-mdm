"""简易雪花算法 ID 生成器（文档要求主键使用雪花算法）."""

from __future__ import annotations

import threading
import time

from app.config import settings


class Snowflake:
    def __init__(self, worker_id: int = 1, datacenter_id: int = 1) -> None:
        self.worker_id = worker_id & 0x1F
        self.datacenter_id = datacenter_id & 0x1F
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()
        self.epoch = 1704067200000  # 2024-01-01 UTC

    def _timestamp(self) -> int:
        return int(time.time() * 1000)

    def next_id(self) -> int:
        with self.lock:
            ts = self._timestamp()
            if ts < self.last_timestamp:
                ts = self.last_timestamp
            if ts == self.last_timestamp:
                self.sequence = (self.sequence + 1) & 0xFFF
                if self.sequence == 0:
                    while ts <= self.last_timestamp:
                        ts = self._timestamp()
            else:
                self.sequence = 0
            self.last_timestamp = ts
            return (
                ((ts - self.epoch) << 22)
                | (self.datacenter_id << 17)
                | (self.worker_id << 12)
                | self.sequence
            )


_generator = Snowflake(
    worker_id=settings.snowflake_worker_id,
    datacenter_id=settings.snowflake_datacenter_id,
)


def snowflake_id() -> int:
    return _generator.next_id()
