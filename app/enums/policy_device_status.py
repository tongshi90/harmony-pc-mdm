"""已废弃：设备策略对齐改为「预期/当前快照匹配」，不再使用任务级状态机.

保留本文件避免旧 import 报错；请勿再写入新业务逻辑。
"""

from __future__ import annotations

# 兼容占位
TARGET = "target"
STAGED = "staged"
PENDING_DISPATCH = "pending_dispatch"
EXECUTING = "executing"
SUCCESS = "success"
FAILED = "failed"
TIMEOUT_DISPLAY = "timeout"
OPEN = frozenset()
ALL = frozenset({TARGET})
LABELS_ZH = {TARGET: "目标"}
