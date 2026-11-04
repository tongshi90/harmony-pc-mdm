from __future__ import annotations

from sqlalchemy.orm import Session

from app.enums.menu import MenuCode, all_menu_codes, get_menu, list_menus, menu_to_dict
from app.models.role import SysRole, SysRoleMenu
from app.models.user import User
from app.services.super_admin import is_builtin_super_admin


def get_role(db: Session, role_id: int | None) -> SysRole | None:
    if not role_id:
        return None
    return (
        db.query(SysRole)
        .filter(SysRole.id == role_id, SysRole.status == 1)
        .first()
    )


def get_user_menu_codes(db: Session, user: User) -> list[str]:
    """内置 admin / is_admin 拥有全部菜单，不受角色限制；否则取角色菜单."""
    if is_builtin_super_admin(user) or user.is_admin == 1:
        return all_menu_codes()
    if not user.role_id:
        return []
    rows = (
        db.query(SysRoleMenu.menu_code)
        .filter(SysRoleMenu.role_id == user.role_id)
        .all()
    )
    codes = [r[0] for r in rows]
    valid = set(all_menu_codes())
    return [c for c in all_menu_codes() if c in codes and c in valid]


def user_has_menu(db: Session, user: User, menu: str | MenuCode) -> bool:
    if is_builtin_super_admin(user) or user.is_admin == 1:
        return True
    code = menu.value if isinstance(menu, MenuCode) else menu
    return code in get_user_menu_codes(db, user)


def build_user_info(db: Session, user: User) -> dict:
    menu_codes = get_user_menu_codes(db, user)
    # 侧栏 /me.menus：隐藏项不返回；menu_codes 仍可含隐藏 Code，便于超管直链调试页
    menus = [
        menu_to_dict(m)
        for c in menu_codes
        if (m := get_menu(c)) is not None and m.visible
    ]

    # 内置超级管理员不绑定角色
    if is_builtin_super_admin(user) or user.is_admin == 1:
        return {
            "id": str(user.id),
            "name": user.name,
            "username": user.username,
            "phone": user.phone,
            "email": user.email,
            "status": user.status,
            "is_admin": 1,
            "role_id": None,
            "role_label": "系统管理员",
            "role": None,
            "menu_codes": menu_codes,
            "menus": menus,
        }

    role = get_role(db, user.role_id)
    return {
        "id": str(user.id),
        "name": user.name,
        "username": user.username,
        "phone": user.phone,
        "email": user.email,
        "status": user.status,
        "is_admin": 0,
        "role_id": str(user.role_id) if user.role_id else None,
        "role_label": role.role_name if role else "未分配角色",
        "role": (
            {
                "id": str(role.id),
                "role_name": role.role_name,
                "role_code": role.role_code,
                "description": role.description,
            }
            if role
            else None
        ),
        "menu_codes": menu_codes,
        "menus": menus,
    }


def list_fixed_menus() -> list[dict]:
    """角色权限勾选用：仅返回可见菜单."""
    return [menu_to_dict(m) for m in list_menus(include_hidden=False)]
