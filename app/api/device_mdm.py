"""对外设备侧 · MDM 最新版本查询（/api/* 白名单，无需登录）."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import no_audit
from app.schemas.common import ok
from app.services import mdm_app_service

router = APIRouter(prefix="/mdm", tags=["设备侧-MDM"])


@router.get("/getInfo")
@no_audit
def get_mdm_info(
    request: Request,
    db: Session = Depends(get_db),
):
    """从云侧获取 MDM 应用最新已发布版本信息."""
    base = str(request.base_url).rstrip("/")
    return ok(mdm_app_service.get_info_for_device(db, public_base_url=base))
