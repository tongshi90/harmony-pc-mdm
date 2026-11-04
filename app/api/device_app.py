"""对外设备侧 · 应用市场（/api/* 白名单，无需登录）."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import no_audit
from app.schemas.common import ok
from app.services import device_app_service

router = APIRouter(prefix="/app", tags=["设备侧-应用"])


@router.get("/list")
@no_audit
def list_apps(
    request: Request,
    SN: str | None = Query(None, description="设备 SN（协议保留）"),
    sn: str | None = Query(None, description="设备 SN"),
    db: Session = Depends(get_db),
):
    """应用市场列表：上架应用 + 最高已发布版本下载地址."""
    _ = (SN, sn)
    base = str(request.base_url).rstrip("/")
    return ok(device_app_service.list_market_apps(db, public_base_url=base))


@router.get("/getInfo")
@no_audit
def get_app_info(
    request: Request,
    appId: str | None = Query(None, description="应用程序 id（业务 app_id）"),
    db: Session = Depends(get_db),
):
    """应用详情：基本信息 + 最新已发布版本下载地址与包大小."""
    base = str(request.base_url).rstrip("/")
    return ok(
        device_app_service.get_market_app_info(
            db, app_id=appId or "", public_base_url=base
        )
    )
