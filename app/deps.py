from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums.menu import MenuCode, match_menu_by_path
from app.models.user import User, UserToken
from app.services.permission_service import user_has_menu
from app.utils.security import decode_token


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> User:
    """登录鉴权：失败统一 HTTP 401（前端据此跳转登录页）."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未登录或令牌缺失")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    jti = payload.get("jti")
    user_id = payload.get("sub")
    if not jti or not user_id:
        raise HTTPException(status_code=401, detail="令牌无效")

    record = db.query(UserToken).filter(UserToken.jti == jti).first()
    if not record:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    if record.expires_time < datetime.utcnow():
        db.delete(record)
        db.commit()
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    user = (
        db.query(User)
        .filter(User.id == int(user_id), User.is_delete == 0)
        .first()
    )
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已删除")
    if user.status != 1:
        raise HTTPException(status_code=401, detail="账号已禁用")

    request.state.token_jti = jti
    request.state.user_id = user.id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_menu(menu: MenuCode) -> Callable[..., User]:
    """菜单权限依赖（注解式用法）:

    @router.get("")
    def api(user: User = Depends(require_menu(MenuCode.PLATFORM))):
        ...
    """

    def _dependency(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not user_has_menu(db, user, menu):
            raise HTTPException(status_code=401, detail="无访问权限，请重新登录或联系管理员")
        return user

    return _dependency


def require_menu_by_path(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """按请求路径自动匹配菜单并校验（适合挂在 Router.dependencies）."""
    item = match_menu_by_path(request.url.path)
    if item and not user_has_menu(db, user, item.code):
        raise HTTPException(status_code=401, detail="无访问权限，请重新登录或联系管理员")
    return user
