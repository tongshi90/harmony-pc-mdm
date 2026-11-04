from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.op_log import SysOpLog
from app.models.user import User
from app.services.super_admin import is_builtin_super_admin
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

SENSITIVE_KEYS = {
    "password",
    "old_password",
    "new_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "private_key",
}
MAX_TEXT = 8000


def _mask_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in SENSITIVE_KEYS:
                out[k] = "******"
            else:
                out[k] = _mask_obj(v)
        return out
    if isinstance(obj, list):
        return [_mask_obj(x) for x in obj]
    return obj


def mask_and_truncate(raw: str | None, limit: int = MAX_TEXT) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        text = json.dumps(_mask_obj(data), ensure_ascii=False)
    except Exception:
        # 非 JSON：粗暴替换常见字段
        for key in SENSITIVE_KEYS:
            if key in text.lower():
                text = "***"
                break
    if len(text) > limit:
        return text[:limit] + "...(truncated)"
    return text


def infer_module(path: str) -> str:
    if path.startswith("/platform/auth"):
        return "授权认证"
    if path.startswith("/platform/platform"):
        return "平台基础管理"
    if path.startswith("/platform/app"):
        return "应用管理"
    if path.startswith("/platform/device"):
        return "设备管理"
    if path.startswith("/platform/member-group"):
        return "成员分组"
    if path.startswith("/platform/member"):
        return "人员管理"
    if path.startswith("/platform/policy"):
        return "策略下发"
    if path.startswith("/platform/dashboard"):
        return "数据看板"
    return "其他"


def infer_action(method: str, path: str) -> str:
    return f"{method} {path}"


def can_view_all_logs(user: User) -> bool:
    """仅内置 admin / is_admin 可看全部."""
    return is_builtin_super_admin(user) or int(user.is_admin or 0) == 1


def create_log(
    db: Session,
    *,
    user_id: int | None,
    username: str | None,
    user_name: str | None,
    module: str | None,
    action: str | None,
    method: str,
    path: str,
    query_params: str | None,
    request_body: str | None,
    success: int,
    response_code: int | None,
    response_message: str | None,
    response_body: str | None,
    client_ip: str | None,
    user_agent: str | None,
    duration_ms: int | None,
) -> None:
    row = SysOpLog(
        id=snowflake_id(),
        user_id=user_id,
        username=(username or "")[:64] or None,
        user_name=(user_name or "")[:64] or None,
        module=(module or "")[:64] or None,
        action=(action or "")[:128] or None,
        method=method[:16],
        path=path[:255],
        query_params=query_params,
        request_body=request_body,
        success=1 if success else 0,
        response_code=response_code,
        response_message=(response_message or "")[:512] or None,
        response_body=response_body,
        client_ip=(client_ip or "")[:64] or None,
        user_agent=(user_agent or "")[:512] or None,
        duration_ms=duration_ms,
        create_time=local_now(),
    )
    db.add(row)
    db.commit()


def _base_query(db: Session, viewer: User, keyword: str | None, success: int | None):
    q = db.query(SysOpLog)
    if not can_view_all_logs(viewer):
        q = q.filter(SysOpLog.user_id == viewer.id)
    if success is not None:
        q = q.filter(SysOpLog.success == success)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            or_(
                SysOpLog.username.like(like),
                SysOpLog.user_name.like(like),
                SysOpLog.action.like(like),
                SysOpLog.module.like(like),
                SysOpLog.path.like(like),
                SysOpLog.client_ip.like(like),
            )
        )
    return q.order_by(SysOpLog.create_time.desc(), SysOpLog.id.desc())


def _fmt_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _to_list_item(row: SysOpLog) -> dict:
    return {
        "id": str(row.id),
        "create_time": _fmt_time(row.create_time),
        "username": row.username or "",
        "user_name": row.user_name or "",
        "module": row.module or "",
        "action": row.action or "",
        "method": row.method or "",
        "path": row.path or "",
        "success": int(row.success or 0),
        "response_message": row.response_message or "",
        "client_ip": row.client_ip or "",
        "duration_ms": row.duration_ms,
    }


def _to_detail(row: SysOpLog) -> dict:
    data = _to_list_item(row)
    data.update(
        {
            "user_id": str(row.user_id) if row.user_id is not None else None,
            "query_params": row.query_params,
            "request_body": row.request_body,
            "response_code": row.response_code,
            "response_body": row.response_body,
            "user_agent": row.user_agent,
        }
    )
    return data


def list_logs(
    db: Session,
    viewer: User,
    *,
    keyword: str | None = None,
    success: int | None = None,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    q = _base_query(db, viewer, keyword, success)
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_to_list_item(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "view_all": can_view_all_logs(viewer),
    }


def get_log(db: Session, viewer: User, log_id: int) -> dict:
    row = db.query(SysOpLog).filter(SysOpLog.id == log_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="日志不存在")
    if not can_view_all_logs(viewer) and row.user_id != viewer.id:
        raise HTTPException(status_code=401, detail="无访问权限，请重新登录或联系管理员")
    return _to_detail(row)


def export_logs_csv(
    db: Session,
    viewer: User,
    *,
    keyword: str | None = None,
    success: int | None = None,
) -> bytes:
    rows = _base_query(db, viewer, keyword, success).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "时间",
            "操作人账号",
            "操作人姓名",
            "模块",
            "动作",
            "方法",
            "接口",
            "成功",
            "返回码",
            "返回信息",
            "IP",
            "耗时(ms)",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                _fmt_time(r.create_time),
                r.username or "",
                r.user_name or "",
                r.module or "",
                r.action or "",
                r.method or "",
                r.path or "",
                "成功" if r.success else "失败",
                r.response_code if r.response_code is not None else "",
                r.response_message or "",
                r.client_ip or "",
                r.duration_ms if r.duration_ms is not None else "",
            ]
        )
    # Excel 友好 UTF-8 BOM
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
