"""对外设备侧 · MDM 版本查询（/api/* 白名单，无需登录）."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
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
    """全局最新已发布版本（用户主动检查更新；不读设备预期）."""
    base = str(request.base_url).rstrip("/")
    return ok(mdm_app_service.get_info_for_device(db, public_base_url=base))


@router.get("/expected")
@no_audit
def get_mdm_expected(
    request: Request,
    sn: str | None = Query(None, description="设备 SN"),
    SN: str | None = Query(None, description="设备 SN（协议字段）"),
    db: Session = Depends(get_db),
):
    """本机平台指定的预期 MDM 版本（启动 / 收到 MDM_UPDATE 后拉取；无预期不回落最新）."""
    base = str(request.base_url).rstrip("/")
    device_sn = (sn or SN or "").strip()
    return ok(
        mdm_app_service.get_expected_for_device(
            db, device_sn, public_base_url=base
        )
    )
