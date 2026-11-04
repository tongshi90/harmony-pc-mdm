"""操作日志注解.

约定（由 AuditLogMiddleware 执行）:
  - POST/PUT/PATCH/DELETE：默认记录（成功/失败均记）
  - GET/HEAD 等查询：默认不记；需要记录时加 @audit_log（如导出）
  - 对外 /api/*、@no_audit：永不记录

用法:
  @audit_log(module="平台基础管理", action="新建管理员")  # 写操作可补充中文描述
  def create_admin(...): ...

  @audit_log(module="平台基础管理", action="导出操作日志")  # 只读但需审计
  def export_op_logs(...): ...

  @no_audit  # 强制跳过（即使是写操作）
  def internal_hook(...): ...
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

AUDIT_ATTR = "__audit__"
NO_AUDIT_ATTR = "__no_audit__"

# 默认会记日志的 HTTP 方法（变更类 / 登录登出等）
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def audit_log(module: str = "", action: str = "") -> Callable[[F], F]:
    """标记需要审计；写操作可只用来补充 module/action，GET 导出等必须加此注解才会记."""

    def decorator(func: F) -> F:
        setattr(func, AUDIT_ATTR, {"module": module or "", "action": action or ""})
        return func

    return decorator


def no_audit(func: F) -> F:
    """明确跳过操作日志."""
    setattr(func, NO_AUDIT_ATTR, True)
    return func


def has_audit_mark(endpoint: Any) -> bool:
    return endpoint is not None and isinstance(getattr(endpoint, AUDIT_ATTR, None), dict)


def get_audit_meta(endpoint: Any) -> dict | None:
    if endpoint is None:
        return None
    if getattr(endpoint, NO_AUDIT_ATTR, False):
        return None
    meta = getattr(endpoint, AUDIT_ATTR, None)
    if isinstance(meta, dict):
        return meta
    return {}
