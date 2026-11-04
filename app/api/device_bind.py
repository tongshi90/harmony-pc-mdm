"""对外设备侧 · 设备绑定（/api/* 白名单，无需登录）.

解绑仅管理台提供：POST /platform/device/{sn}/unbind（需登录 + 设备管理权限）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import no_audit
from app.schemas.common import ok
from app.schemas.device_bind import DeviceBindIn
from app.services import device_bind_service

router = APIRouter(prefix="/device", tags=["设备侧-绑定"])


@router.post("/bind")
@no_audit
def bind_device(body: DeviceBindIn, db: Session = Depends(get_db)):
    """设备与成员绑定（临时方案：密码明文传输，后续对接企业认证）.

    若该设备与该成员已相互绑定，幂等返回成功，便于端侧重试。
    """
    return ok(
        device_bind_service.bind_device(
            db,
            sn=body.SN,
            user_name=body.userName,
            password=body.password,
        )
    )
