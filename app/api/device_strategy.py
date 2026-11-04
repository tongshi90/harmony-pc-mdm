"""对外设备侧 · 策略配置拉取（/api/* 白名单，无需登录）."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import no_audit
from app.schemas.common import ok
from app.services import policy_dispatch_service

router = APIRouter(prefix="/strategy", tags=["设备侧-策略"])


@router.get("/get")
@no_audit
def get_strategy(
    sn: str | None = Query(None, description="设备 SN"),
    SN: str | None = Query(None, description="设备 SN（协议字段）"),
    db: Session = Depends(get_db),
):
    """设备收到 MQTT STRATEGY_PULL 或启动时拉取全量预期策略.

    返回最新策略任务的紧急度/最晚执行时间，以及该 SN 全部预期快照。
    若设备已解绑：返回空 snapshot，并补发 DEVICE_UNBINDING MQTT。
    """
    device_sn = (sn or SN or "").strip()
    return ok(policy_dispatch_service.get_strategy_for_device(db, device_sn))
