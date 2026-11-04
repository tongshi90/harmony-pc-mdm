"""业务时间工具.

业务库表中的 create_time / update_time / 操作日志时间等，统一使用本机本地时间
（部署在东八区即为北京时间），接口原样格式化展示，避免 utcnow 导致差 8 小时。

JWT 过期时间等鉴权相关仍使用 UTC（见 app.utils.security），勿混用本模块。
"""

from __future__ import annotations

from datetime import datetime


def now() -> datetime:
    """当前本地时间（无时区信息，与 SQLite DateTime 一致）."""
    return datetime.now()
