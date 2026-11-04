from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User, UserToken
from app.services.permission_service import build_user_info
from app.utils.crypto import decrypt_password
from app.utils.password_rules import assert_platform_password
from app.utils.security import create_access_token, hash_password, verify_password
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now


def to_user_info(db: Session, user: User) -> dict:
    return build_user_info(db, user)


def login(db: Session, username: str, password_cipher: str, client_ip: str) -> dict:
    try:
        password = decrypt_password(password_cipher)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="密码解密失败，请刷新页面重试") from exc

    user = (
        db.query(User)
        .filter(User.username == username, User.is_delete == 0)
        .first()
    )
    if not user:
        raise HTTPException(status_code=400, detail="账号或密码错误")
    if not verify_password(password, user.password):
        raise HTTPException(status_code=400, detail="账号或密码错误")
    if user.status != 1:
        raise HTTPException(status_code=401, detail="账号已禁用")

    token, jti, expire = create_access_token(user.id)
    # login_time / create_time：业务本地时间；expires_time：与 JWT exp 一致（UTC）
    logged_at = local_now()
    db.add(
        UserToken(
            id=snowflake_id(),
            jti=jti,
            user_id=user.id,
            login_time=logged_at,
            expires_time=expire,
            client_ip=client_ip or None,
            create_time=logged_at,
        )
    )
    db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": to_user_info(db, user),
    }


def logout(db: Session, jti: str | None) -> None:
    if not jti:
        return
    record = db.query(UserToken).filter(UserToken.jti == jti).first()
    if record:
        db.delete(record)
        db.commit()


def change_password(
    db: Session, user: User, old_cipher: str, new_cipher: str
) -> None:
    try:
        old_password = decrypt_password(old_cipher)
        new_password = decrypt_password(new_cipher)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="密码解密失败，请刷新页面重试") from exc

    if not verify_password(old_password, user.password):
        raise HTTPException(status_code=400, detail="旧密码不正确")
    # 仅校验新密码格式；旧密码不套新规则（历史弱密码仍可用来验证身份）
    assert_platform_password(new_password)
    if new_password == old_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")

    user.password = hash_password(new_password)
    db.query(UserToken).filter(UserToken.user_id == user.id).delete()
    db.commit()
