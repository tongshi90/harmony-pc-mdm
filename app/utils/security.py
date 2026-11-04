from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str | int, expires_delta: timedelta | None = None) -> tuple[str, str, datetime]:
    """返回 (token, jti, expires_at)."""
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    jti = uuid4().hex
    payload: dict[str, Any] = {"sub": str(subject), "jti": jti, "exp": expire}
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return token, jti, expire


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise ValueError("无效或过期的令牌") from exc
