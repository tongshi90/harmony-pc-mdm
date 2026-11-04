"""全局 API 鉴权：云侧 /platform 除白名单外均需登录；菜单路径按前缀校验权限.

对外设备侧接口统一挂在 /api/ 下，默认不鉴权（交互文档已约定，勿改前缀）。
企业对接 OpenAPI 挂在 /openapi/ 下，非 /platform 前缀故自然放行（白名单、暂无签名；
日后加签也不改路径前缀）。勿把 /openapi 误并入 /platform 鉴权。
"""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import SessionLocal
from app.enums.menu import match_menu_by_path
from app.models.user import User, UserToken
from app.schemas.common import fail
from app.services.permission_service import user_has_menu
from app.utils.security import decode_token

# 云侧管理台：无需登录
PUBLIC_PATHS = {
    "/platform/health",
    "/platform/auth/login",
    "/platform/auth/public-key",
}

# 设备侧下载 HAP：/platform/app/{appId}/versions/{versionId}/package
_PUBLIC_APP_PACKAGE_RE = re.compile(
    r"^/platform/app/\d+/versions/\d+/package$"
)
# MDM Agent 安装包：/platform/mdm-app/versions/{versionId}/package
_PUBLIC_MDM_PACKAGE_RE = re.compile(
    r"^/platform/mdm-app/versions/\d+/package$"
)
# 应用图标：列表/详情 <img> 直链，免登录
_PUBLIC_APP_ICON_RE = re.compile(r"^/platform/app/\d+/icon$")

# 需登录但不校验菜单（个人中心）
AUTH_ONLY_PREFIXES = ("/platform/auth/",)


def _is_platform_api(path: str) -> bool:
    return path == "/platform" or path.startswith("/platform/")


def _is_public_platform_path(path: str, method: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    # 应用安装包下载：设备按 bundleDownloadUrl 直链拉取，免登录
    if method.upper() == "GET" and _PUBLIC_APP_PACKAGE_RE.match(path):
        return True
    # MDM Agent 安装包下载
    if method.upper() == "GET" and _PUBLIC_MDM_PACKAGE_RE.match(path):
        return True
    # 应用图标直链（管理台 img 标签）
    if method.upper() == "GET" and _PUBLIC_APP_ICON_RE.match(path):
        return True
    return False


class AuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # 对外 /api/*：白名单开放，不鉴权
        if path.startswith("/api/"):
            return await call_next(request)
        # 非云侧管理台接口（静态页等）直接放行
        if not _is_platform_api(path):
            return await call_next(request)
        if _is_public_platform_path(path, request.method):
            return await call_next(request)

        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            return JSONResponse(
                status_code=401,
                content=fail("未登录或令牌缺失", code=401),
            )
        token = auth.split(" ", 1)[1].strip()
        db = SessionLocal()
        try:
            try:
                payload = decode_token(token)
            except ValueError as exc:
                return JSONResponse(
                    status_code=401, content=fail(str(exc), code=401)
                )
            jti = payload.get("jti")
            user_id = payload.get("sub")
            if not jti or not user_id:
                return JSONResponse(
                    status_code=401, content=fail("令牌无效", code=401)
                )
            record = db.query(UserToken).filter(UserToken.jti == jti).first()
            if not record:
                return JSONResponse(
                    status_code=401,
                    content=fail("登录已失效，请重新登录", code=401),
                )
            if record.expires_time < datetime.utcnow():
                db.delete(record)
                db.commit()
                return JSONResponse(
                    status_code=401,
                    content=fail("登录已过期，请重新登录", code=401),
                )
            user = (
                db.query(User)
                .filter(User.id == int(user_id), User.is_delete == 0)
                .first()
            )
            if not user or user.status != 1:
                return JSONResponse(
                    status_code=401,
                    content=fail("账号不可用，请重新登录", code=401),
                )

            # 菜单路径权限
            if not path.startswith(AUTH_ONLY_PREFIXES):
                menu = match_menu_by_path(path)
                if menu and not user_has_menu(db, user, menu.code):
                    return JSONResponse(
                        status_code=401,
                        content=fail("无访问权限，请重新登录或联系管理员", code=401),
                    )

            request.state.token_jti = jti
            request.state.user_id = user.id
        finally:
            db.close()

        return await call_next(request)
