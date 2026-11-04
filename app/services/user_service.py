from __future__ import annotations

import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.role import SysRole
from app.models.user import User, UserToken
from app.services.super_admin import is_builtin_super_admin, is_builtin_super_admin_username
from app.utils.crypto import decrypt_password
from app.utils.password_rules import assert_platform_password
from app.utils.security import hash_password
from app.utils.snowflake import snowflake_id

_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _validate_phone(phone: str | None) -> str | None:
    phone = _normalize_optional(phone)
    if phone is None:
        return None
    if not _PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    return phone


def _validate_email(email: str | None) -> str | None:
    email = _normalize_optional(email)
    if email is None:
        return None
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    return email


def _assert_unique_fields(
    db: Session,
    *,
    username: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    exclude_user_id: int | None = None,
) -> None:
    """唯一性仅针对未删除账号（逻辑删除后的账号/手机/邮箱可复用）."""
    if username:
        q = db.query(User).filter(User.username == username, User.is_delete == 0)
        if exclude_user_id is not None:
            q = q.filter(User.id != exclude_user_id)
        if q.first():
            raise HTTPException(status_code=400, detail="登录账号已存在")
    if phone:
        q = db.query(User).filter(User.phone == phone, User.is_delete == 0)
        if exclude_user_id is not None:
            q = q.filter(User.id != exclude_user_id)
        if q.first():
            raise HTTPException(status_code=400, detail="手机号已被使用")
    if email:
        q = db.query(User).filter(User.email == email, User.is_delete == 0)
        if exclude_user_id is not None:
            q = q.filter(User.id != exclude_user_id)
        if q.first():
            raise HTTPException(status_code=400, detail="邮箱已被使用")


def _last_login_map(db: Session, user_ids: list[int]) -> dict[int, datetime]:
    if not user_ids:
        return {}
    rows = (
        db.query(UserToken.user_id, func.max(UserToken.login_time))
        .filter(UserToken.user_id.in_(user_ids))
        .group_by(UserToken.user_id)
        .all()
    )
    return {uid: ts for uid, ts in rows}


def _role_name_map(db: Session, role_ids: list[int]) -> dict[int, str]:
    ids = [i for i in role_ids if i]
    if not ids:
        return {}
    rows = db.query(SysRole.id, SysRole.role_name).filter(SysRole.id.in_(ids)).all()
    return {rid: name for rid, name in rows}


def _to_out(
    user: User,
    last_login: datetime | None = None,
    role_name: str | None = None,
) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "name": user.name,
        "phone": user.phone,
        "email": user.email,
        "status": user.status,
        "is_admin": 0,
        "role_id": str(user.role_id) if user.role_id else None,
        "role_label": role_name or "未分配角色",
        "last_login": last_login.strftime("%Y-%m-%d %H:%M:%S") if last_login else None,
    }


def _resolve_role_id(db: Session, role_id_raw: str | None) -> int | None:
    if role_id_raw is None or role_id_raw == "":
        return None
    try:
        rid = int(role_id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="角色 ID 无效") from exc
    role = db.query(SysRole).filter(SysRole.id == rid, SysRole.status == 1).first()
    if not role:
        raise HTTPException(status_code=400, detail="角色不存在或已禁用")
    return rid


def _get_managed_user(db: Session, user_id: int) -> User:
    """获取可管理的管理员；内置 admin 视为不存在."""
    user = db.query(User).filter(User.id == user_id, User.is_delete == 0).first()
    if not user or is_builtin_super_admin(user):
        raise HTTPException(status_code=404, detail="管理员不存在")
    return user


def list_admins(
    db: Session,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 12,
) -> dict:
    # 内置超级管理员不出现在列表中（按账号名 + is_admin 双重排除）
    q = db.query(User).filter(
        User.is_delete == 0,
        User.username != settings.default_admin_username,
        User.is_admin != 1,
    )
    if keyword:
        like = f"%{keyword.strip()}%"
        q = q.filter(
            or_(
                User.username.like(like),
                User.name.like(like),
                User.phone.like(like),
                User.email.like(like),
            )
        )
    total = q.count()
    items = (
        q.order_by(User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    login_map = _last_login_map(db, [u.id for u in items])
    role_map = _role_name_map(db, [u.role_id for u in items if u.role_id])
    return {
        "items": [
            _to_out(u, login_map.get(u.id), role_map.get(u.role_id) if u.role_id else None)
            for u in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_admin(db: Session, user_id: int) -> dict:
    user = _get_managed_user(db, user_id)
    login_map = _last_login_map(db, [user.id])
    role_map = _role_name_map(db, [user.role_id] if user.role_id else [])
    return _to_out(
        user,
        login_map.get(user.id),
        role_map.get(user.role_id) if user.role_id else None,
    )


def create_admin(db: Session, data) -> dict:
    username = data.username.strip()
    if is_builtin_super_admin_username(username):
        raise HTTPException(status_code=400, detail="该账号名为系统保留，不可创建")
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="登录账号至少 2 位")

    phone = _validate_phone(data.phone)
    email = _validate_email(data.email)
    _assert_unique_fields(db, username=username, phone=phone, email=email)

    try:
        password = decrypt_password(data.password)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="密码解密失败") from exc
    assert_platform_password(password)

    if not data.role_id:
        raise HTTPException(status_code=400, detail="请选择角色")
    role_id = _resolve_role_id(db, data.role_id)

    user = User(
        id=snowflake_id(),
        username=username,
        name=data.name.strip(),
        phone=phone,
        email=email,
        password=hash_password(password),
        status=1,  # 新建默认启用；启停改由列表卡片操作
        is_delete=0,
        is_admin=0,  # 仅内置 admin 可为超级管理员
        role_id=role_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    role_map = _role_name_map(db, [user.role_id] if user.role_id else [])
    return _to_out(user, None, role_map.get(user.role_id) if user.role_id else None)


def update_admin(db: Session, user_id: int, data, operator: User) -> dict:
    """编辑不允许修改账号与密码."""
    user = _get_managed_user(db, user_id)

    if data.name is not None:
        user.name = data.name.strip()
    if data.phone is not None:
        phone = _validate_phone(data.phone)
        _assert_unique_fields(db, phone=phone, exclude_user_id=user.id)
        user.phone = phone
    if data.email is not None:
        email = _validate_email(data.email)
        _assert_unique_fields(db, email=email, exclude_user_id=user.id)
        user.email = email
    if data.status is not None:
        if user.id == operator.id and data.status == 0:
            raise HTTPException(status_code=400, detail="不能禁用当前登录账号")
        user.status = data.status
    user.is_admin = 0
    if data.role_id is not None:
        if data.role_id == "":
            raise HTTPException(status_code=400, detail="请选择角色")
        user.role_id = _resolve_role_id(db, data.role_id)

    db.commit()
    db.refresh(user)
    login_map = _last_login_map(db, [user.id])
    role_map = _role_name_map(db, [user.role_id] if user.role_id else [])
    return _to_out(
        user,
        login_map.get(user.id),
        role_map.get(user.role_id) if user.role_id else None,
    )


def soft_delete_admin(db: Session, user_id: int, operator: User) -> None:
    user = _get_managed_user(db, user_id)
    if user.id == operator.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    user.username = f"{user.username}__del__{user.id}"
    user.is_delete = 1
    user.status = 0
    db.query(UserToken).filter(UserToken.user_id == user.id).delete()
    db.commit()


def set_admin_status(db: Session, user_id: int, status: int, operator: User) -> dict:
    user = _get_managed_user(db, user_id)
    if user.id == operator.id and status == 0:
        raise HTTPException(status_code=400, detail="不能禁用当前登录账号")
    user.status = status
    if status == 0:
        db.query(UserToken).filter(UserToken.user_id == user.id).delete()
    db.commit()
    db.refresh(user)
    login_map = _last_login_map(db, [user.id])
    role_map = _role_name_map(db, [user.role_id] if user.role_id else [])
    return _to_out(
        user,
        login_map.get(user.id),
        role_map.get(user.role_id) if user.role_id else None,
    )


def reset_password(db: Session, user_id: int, password_cipher: str) -> None:
    user = _get_managed_user(db, user_id)
    try:
        password = decrypt_password(password_cipher)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="密码解密失败") from exc
    assert_platform_password(password)
    user.password = hash_password(password)
    db.query(UserToken).filter(UserToken.user_id == user.id).delete()
    db.commit()
