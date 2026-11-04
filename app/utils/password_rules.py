"""平台管理员密码规则（仅约束新设/重置/修改后的新密码；登录与旧密码不校验格式）."""

from __future__ import annotations

import re

from fastapi import HTTPException

# 6–18 位，须同时含字母与数字；大小写与特殊符号不限
PLATFORM_PASSWORD_HINT = "密码须为 6-18 位，且同时包含字母和数字"
_PLATFORM_PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{6,18}$")


def is_valid_platform_password(password: str) -> bool:
    if password is None:
        return False
    # 不允许中间换行等空白控制字符以外的随意空白？规则未禁止空格，仅要求长度与字母数字。
    return bool(_PLATFORM_PASSWORD_RE.fullmatch(password))


def assert_platform_password(password: str, *, detail: str | None = None) -> None:
    if not is_valid_platform_password(password):
        raise HTTPException(status_code=400, detail=detail or PLATFORM_PASSWORD_HINT)
