from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log, no_audit
from app.deps import get_client_ip, get_current_user
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest
from app.schemas.common import ok
from app.services import auth_service
from app.utils.crypto import get_public_key_pem

router = APIRouter()


@router.get("/public-key")
@no_audit
def public_key():
    return ok({"public_key": get_public_key_pem(), "algorithm": "RSA-OAEP-SHA256"})


@router.post("/login")
@audit_log(module="授权认证", action="登录")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    data = auth_service.login(db, body.username, body.password, get_client_ip(request))
    return ok(data)


@router.post("/logout")
@audit_log(module="授权认证", action="退出登录")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),  # noqa: ARG001
):
    auth_service.logout(db, getattr(request.state, "token_jti", None))
    return ok()


@router.get("/me")
@no_audit
def me(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return ok(auth_service.to_user_info(db, current))


@router.put("/password")
@audit_log(module="授权认证", action="修改密码")
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    auth_service.change_password(db, current, body.old_password, body.new_password)
    return ok()
