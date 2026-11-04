from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.enums.menu import all_menu_codes, get_menu
from app.enums.system_role import SYSTEM_ROLE_CODES, system_role_defs
from app.models.role import SysRole, SysRoleMenu
from app.models.user import User
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now


def _is_system_role(role: SysRole) -> bool:
    return int(getattr(role, "is_system", 0) or 0) == 1 or (
        role.role_code in SYSTEM_ROLE_CODES
    )


def _assert_mutable(role: SysRole) -> None:
    if _is_system_role(role):
        raise HTTPException(
            status_code=400,
            detail="系统角色不可编辑、禁用、删除或修改权限",
        )


def _role_out(db: Session, role: SysRole) -> dict:
    menus = [
        r.menu_code
        for r in db.query(SysRoleMenu).filter(SysRoleMenu.role_id == role.id).all()
    ]
    valid = set(all_menu_codes())
    menus = [c for c in all_menu_codes() if c in menus and c in valid]
    user_count = (
        db.query(func.count(User.id))
        .filter(User.role_id == role.id, User.is_delete == 0)
        .scalar()
        or 0
    )
    is_system = 1 if _is_system_role(role) else 0
    return {
        "id": str(role.id),
        "role_name": role.role_name,
        "role_code": role.role_code,
        "description": role.description,
        "status": role.status,
        "is_system": is_system,
        "menu_codes": menus,
        "menus": [
            {"code": c, "name": get_menu(c).name if get_menu(c) else c} for c in menus
        ],
        "user_count": int(user_count),
        "create_time": role.create_time.strftime("%Y-%m-%d %H:%M:%S") if role.create_time else None,
        "update_time": role.update_time.strftime("%Y-%m-%d %H:%M:%S") if role.update_time else None,
    }


def list_roles(db: Session, keyword: str | None = None) -> list[dict]:
    q = db.query(SysRole)
    if keyword:
        like = f"%{keyword.strip()}%"
        q = q.filter(
            (SysRole.role_name.like(like)) | (SysRole.role_code.like(like))
        )
    # 系统角色靠前，再按 id
    roles = q.order_by(SysRole.is_system.desc(), SysRole.id.asc()).all()
    return [_role_out(db, r) for r in roles]


def get_role(db: Session, role_id: int) -> dict:
    role = db.query(SysRole).filter(SysRole.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    return _role_out(db, role)


def _validate_menus(menu_codes: list[str]) -> list[str]:
    valid = set(all_menu_codes())
    cleaned = []
    for code in menu_codes or []:
        if code not in valid:
            raise HTTPException(status_code=400, detail=f"无效菜单: {code}")
        if code not in cleaned:
            cleaned.append(code)
    return cleaned


def _replace_menus(db: Session, role_id: int, menu_codes: list[str]) -> None:
    db.query(SysRoleMenu).filter(SysRoleMenu.role_id == role_id).delete()
    now = local_now()
    for code in menu_codes:
        db.add(
            SysRoleMenu(
                id=snowflake_id(),
                role_id=role_id,
                menu_code=code,
                create_time=now,
            )
        )


def ensure_system_roles(db: Session) -> None:
    """启动引导：确保三个内置系统角色存在且菜单/状态与定义一致."""
    now = local_now()
    valid = set(all_menu_codes())
    # 清理已下线菜单码（如历史 policy_manage）
    db.query(SysRoleMenu).filter(~SysRoleMenu.menu_code.in_(list(valid))).delete(
        synchronize_session=False
    )
    for spec in system_role_defs():
        role = db.query(SysRole).filter(SysRole.role_code == spec.role_code).first()
        menus = _validate_menus(list(spec.menu_codes))
        if role:
            role.role_name = spec.role_name
            role.description = spec.description
            role.status = 1
            role.is_system = 1
            role.update_time = now
            _replace_menus(db, role.id, menus)
        else:
            role = SysRole(
                id=snowflake_id(),
                role_name=spec.role_name,
                role_code=spec.role_code,
                description=spec.description,
                status=1,
                is_system=1,
                create_time=now,
                update_time=now,
            )
            db.add(role)
            db.flush()
            _replace_menus(db, role.id, menus)
    db.commit()


def create_role(db: Session, data) -> dict:
    code = data.role_code.strip()
    if code in SYSTEM_ROLE_CODES:
        raise HTTPException(status_code=400, detail="该角色编码为系统保留，请更换")
    exists = db.query(SysRole).filter(SysRole.role_code == code).first()
    if exists:
        raise HTTPException(status_code=400, detail="角色编码已存在")
    menus = _validate_menus(data.menu_codes)
    now = local_now()
    role = SysRole(
        id=snowflake_id(),
        role_name=data.role_name.strip(),
        role_code=code,
        description=data.description,
        status=data.status,
        is_system=0,
        create_time=now,
        update_time=now,
    )
    db.add(role)
    db.flush()
    _replace_menus(db, role.id, menus)
    db.commit()
    db.refresh(role)
    return _role_out(db, role)


def update_role(db: Session, role_id: int, data) -> dict:
    role = db.query(SysRole).filter(SysRole.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    _assert_mutable(role)
    if data.role_name is not None:
        role.role_name = data.role_name.strip()
    if data.description is not None:
        role.description = data.description
    if data.status is not None:
        role.status = data.status
    if data.menu_codes is not None:
        _replace_menus(db, role.id, _validate_menus(data.menu_codes))
    role.update_time = local_now()
    db.commit()
    db.refresh(role)
    return _role_out(db, role)


def delete_role(db: Session, role_id: int) -> None:
    role = db.query(SysRole).filter(SysRole.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    _assert_mutable(role)
    used = (
        db.query(func.count(User.id))
        .filter(User.role_id == role_id, User.is_delete == 0)
        .scalar()
        or 0
    )
    if used > 0:
        raise HTTPException(status_code=400, detail="角色正在使用中，无法删除")
    db.query(SysRoleMenu).filter(SysRoleMenu.role_id == role_id).delete()
    db.delete(role)
    db.commit()


def set_role_status(db: Session, role_id: int, status: int) -> dict:
    role = db.query(SysRole).filter(SysRole.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    _assert_mutable(role)
    if status == 0:
        used = (
            db.query(func.count(User.id))
            .filter(User.role_id == role_id, User.is_delete == 0)
            .scalar()
            or 0
        )
        if used > 0:
            raise HTTPException(status_code=400, detail="角色正在使用中，无法禁用")
    role.status = status
    role.update_time = local_now()
    db.commit()
    db.refresh(role)
    return _role_out(db, role)
