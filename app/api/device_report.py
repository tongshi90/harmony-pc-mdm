"""对外设备侧 · 上报接口（/api/* 白名单，无需登录）."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import no_audit
from app.schemas.common import ok
from app.schemas.device_report import LocationReportIn, SnapshotReportIn
from app.services import device_report_service

router = APIRouter(prefix="/report", tags=["设备侧-上报"])


@router.post("/location")
@no_audit
def report_location(body: LocationReportIn, db: Session = Depends(get_db)):
    """设备位置上报：写入 t_device_location_log."""
    return ok(
        device_report_service.report_location(
            db,
            sn=body.SN,
            longitude=body.longitude,
            latitude=body.latitude,
        )
    )


@router.post("/snapshot")
@no_audit
def report_snapshot(body: SnapshotReportIn, db: Session = Depends(get_db)):
    """设备当前快照上报：全量覆盖策略当前快照 + 已装应用；deviceInfo 仅 basic_info_synced=0 时写入."""
    return ok(
        device_report_service.report_snapshot(
            db,
            sn=body.SN,
            snapshot=body.snapshot,
            app_infos=body.appInfos,
            device_info=body.deviceInfo,
        )
    )
