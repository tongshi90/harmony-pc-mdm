"""操作日志中间件.

规则:
  - 仅云侧 /platform/* 参与审计
  - POST/PUT/PATCH/DELETE 默认记录（登录、改密、增删改等）
  - GET 等查询默认不记；加了 @audit_log 的才记（如导出）
  - 对外 /api/*、@no_audit、健康检查等永不记录
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import parse_qs

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.database import SessionLocal
from app.decorators.audit import (
    MUTATING_METHODS,
    NO_AUDIT_ATTR,
    get_audit_meta,
    has_audit_mark,
)
from app.models.user import User
from app.services import op_log_service

# 永不记录
SKIP_EXACT = {
    "/platform/health",
    "/platform/auth/public-key",
    "/platform/auth/me",
}
# 前缀永不记录（预留；对外 /api/* 已由路径前缀整体跳过）
SKIP_PREFIXES: tuple[str, ...] = ()

MAX_BODY_READ = 64 * 1024


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


def _should_audit(method: str, path: str, endpoint: Any) -> bool:
    # 仅云侧管理台；对外 /api/* 不记日志
    if not (path == "/platform" or path.startswith("/platform/")):
        return False
    if path in SKIP_EXACT:
        return False
    if any(path.startswith(p) for p in SKIP_PREFIXES):
        return False
    if endpoint is not None and getattr(endpoint, NO_AUDIT_ATTR, False):
        return False
    # 写操作 / 登录登出等：默认记
    if method in MUTATING_METHODS:
        return True
    # 查询类：仅显式 @audit_log 才记（导出等）
    return has_audit_mark(endpoint)


def _parse_json_safe(raw: bytes | str | None) -> Any:
    if not raw:
        return None
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except Exception:
            return None
    else:
        text = raw
    try:
        return json.loads(text)
    except Exception:
        return text


def _extract_username_hint(body_bytes: bytes) -> str | None:
    data = _parse_json_safe(body_bytes)
    if isinstance(data, dict):
        u = data.get("username")
        if isinstance(u, str) and u.strip():
            return u.strip()
    return None


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # 预读 body，供后续路由与日志使用
        body_bytes = b""
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            body_bytes = await request.body()
            if len(body_bytes) > MAX_BODY_READ:
                body_bytes = body_bytes[:MAX_BODY_READ]

            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            request = Request(request.scope, receive)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        endpoint = None
        route = request.scope.get("route")
        if route is not None:
            endpoint = getattr(route, "endpoint", None)

        if not _should_audit(method, path, endpoint):
            return response

        # 读取响应体（再封装回去）
        resp_chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            resp_chunks.append(chunk)
        resp_body = b"".join(resp_chunks)

        new_response = Response(
            content=resp_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
        # 重新计算长度
        if "content-length" in new_response.headers:
            del new_response.headers["content-length"]

        try:
            self._write_log(
                request=request,
                method=method,
                path=path,
                body_bytes=body_bytes,
                resp_body=resp_body,
                http_status=response.status_code,
                duration_ms=duration_ms,
                endpoint=endpoint,
            )
        except Exception:
            # 审计失败不影响业务
            pass

        return new_response

    def _write_log(
        self,
        *,
        request: Request,
        method: str,
        path: str,
        body_bytes: bytes,
        resp_body: bytes,
        http_status: int,
        duration_ms: int,
        endpoint: Any,
    ) -> None:
        meta = get_audit_meta(endpoint) or {}
        module = (meta.get("module") or "").strip() or op_log_service.infer_module(path)
        action = (meta.get("action") or "").strip() or op_log_service.infer_action(method, path)

        query = request.url.query or ""
        query_masked = op_log_service.mask_and_truncate(query) if query else None
        # query 也可能含敏感：统一走 JSON 路径不太合适，简单截断
        if query and len(query) > 2000:
            query_masked = query[:2000] + "...(truncated)"
        elif query:
            # 对 query 做字段级脱敏
            try:
                parsed = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(query).items()}
                query_masked = json.dumps(
                    op_log_service._mask_obj(parsed), ensure_ascii=False
                )
            except Exception:
                query_masked = query[:2000]

        req_text = body_bytes.decode("utf-8", errors="replace") if body_bytes else None
        request_body = op_log_service.mask_and_truncate(req_text)

        resp_text = resp_body.decode("utf-8", errors="replace") if resp_body else ""
        biz_code = http_status
        biz_msg = ""
        success = 1 if 200 <= http_status < 400 else 0
        try:
            payload = json.loads(resp_text) if resp_text else None
            if isinstance(payload, dict) and "code" in payload:
                biz_code = int(payload.get("code") or 0)
                biz_msg = str(payload.get("message") or "")
                success = 1 if biz_code == 0 else 0
        except Exception:
            payload = None

        response_body = op_log_service.mask_and_truncate(resp_text)

        user_id = getattr(request.state, "user_id", None)
        username = None
        user_name = None
        db = SessionLocal()
        try:
            if user_id is not None:
                user = db.query(User).filter(User.id == int(user_id)).first()
                if user:
                    username = user.username
                    user_name = user.name
            # 登录接口此时尚无 request.state.user_id，从请求/响应补全操作人
            if path == "/platform/auth/login":
                if not username:
                    username = _extract_username_hint(body_bytes)
                try:
                    payload = json.loads(resp_body.decode("utf-8")) if resp_body else None
                    user_info = ((payload or {}).get("data") or {}).get("user") or {}
                    if user_info.get("id") is not None:
                        user_id = user_info.get("id")
                    if user_info.get("username"):
                        username = user_info.get("username")
                    if user_info.get("name"):
                        user_name = user_info.get("name")
                except Exception:
                    pass

            op_log_service.create_log(
                db,
                user_id=int(user_id) if user_id is not None else None,
                username=username,
                user_name=user_name,
                module=module,
                action=action,
                method=method,
                path=path,
                query_params=query_masked,
                request_body=request_body,
                success=success,
                response_code=biz_code,
                response_message=biz_msg or ("" if success else f"HTTP {http_status}"),
                response_body=response_body,
                client_ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
                duration_ms=duration_ms,
            )
        finally:
            db.close()
