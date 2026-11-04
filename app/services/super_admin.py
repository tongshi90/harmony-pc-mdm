"""内置超级管理员（username=admin）：天然全权限，不受角色限制，不出现在管理员列表."""

from __future__ import annotations

from app.config import settings
from app.models.user import User


def is_builtin_super_admin(user: User | None) -> bool:
    if not user:
        return False
    return user.username == settings.default_admin_username


def is_builtin_super_admin_username(username: str | None) -> bool:
    return bool(username) and username == settings.default_admin_username
