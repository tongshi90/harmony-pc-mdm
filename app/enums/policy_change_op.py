"""策略预期变更日志 · 操作类型（t_policy_task.op_type）.

三种来源共用 task / item / device 三表；设备对齐仍看 expected vs current 快照。

策略紧急度默认约定：
  - dispatch：按管理台前端选择
  - app_batch：固定普通策略，最多等待 24 小时
  - initial_bind：固定紧急策略（立即执行）
"""

from __future__ import annotations

from typing import Any

# 策略下发（管理台「策略下发」）
DISPATCH = "dispatch"
# 设备绑定后套用初始策略模板（预留）
INITIAL_BIND = "initial_bind"
# 应用批量安装/卸载（装/卸由 item.param 区分，不拆两个 op_type）
APP_BATCH = "app_batch"

ALL = frozenset({DISPATCH, INITIAL_BIND, APP_BATCH})

LABELS_ZH = {
    DISPATCH: "自定义策略下发",
    INITIAL_BIND: "初始策略下发",
    APP_BATCH: "应用批量操作",
}

# 各来源默认紧急度（dispatch 无固定默认，由前端传入）
LEVEL_NORMAL = "normal"
LEVEL_URGENT = "urgent"

# 应用批量安装/卸载
APP_BATCH_DEFAULT_LEVEL = LEVEL_NORMAL
APP_BATCH_DEFAULT_WAIT_HOURS = 24

# 初始策略绑定
INITIAL_BIND_DEFAULT_LEVEL = LEVEL_URGENT


def default_level_for_op(op_type: str) -> str | None:
    """返回该变更来源的默认策略类型；dispatch 返回 None（须由调用方指定）."""
    ot = (op_type or "").strip()
    if ot == APP_BATCH:
        return APP_BATCH_DEFAULT_LEVEL
    if ot == INITIAL_BIND:
        return INITIAL_BIND_DEFAULT_LEVEL
    return None


def default_wait_hours_for_op(op_type: str) -> int | None:
    """返回该变更来源在普通策略下的默认等待小时；紧急或不适用为 None."""
    ot = (op_type or "").strip()
    if ot == APP_BATCH:
        return APP_BATCH_DEFAULT_WAIT_HOURS
    return None


def resolve_policy_timing(
    *,
    op_type: str,
    policy_level: str | None = None,
    wait_hours: int | None = None,
    now: Any = None,
) -> tuple[str, int | None, Any]:
    """解析写入 t_policy_task 的 policy_level / wait_hours / deadline_at.

    - dispatch：使用传入的 policy_level / wait_hours（普通策略必填等待时间）
    - app_batch：强制普通 + 24h
    - initial_bind：强制紧急（无等待、无截止）
    """
    from datetime import timedelta

    from app.utils.timeutil import now as local_now

    ts = now or local_now()
    ot = (op_type or DISPATCH).strip() or DISPATCH

    if ot == APP_BATCH:
        hours = APP_BATCH_DEFAULT_WAIT_HOURS
        return APP_BATCH_DEFAULT_LEVEL, hours, ts + timedelta(hours=hours)

    if ot == INITIAL_BIND:
        return INITIAL_BIND_DEFAULT_LEVEL, None, None

    # dispatch：尊重调用方
    level = (policy_level or LEVEL_NORMAL).strip() or LEVEL_NORMAL
    if level == LEVEL_URGENT:
        return LEVEL_URGENT, None, None
    hours = int(wait_hours) if wait_hours is not None else 4
    return LEVEL_NORMAL, hours, ts + timedelta(hours=hours)
