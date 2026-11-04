"""对外设备侧 · 业务卡片拉取（/api/biz-card/* 白名单，无需登录）."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import no_audit
from app.schemas.common import ok
from app.services import biz_card_agent_service

router = APIRouter(prefix="/biz-card", tags=["设备侧-业务卡片"])


def _sn(sn: str | None, SN: str | None) -> str:
    return (sn or SN or "").strip()


@router.get("/todos")
@no_audit
def list_todos(
    sn: str | None = Query(None, description="设备 SN"),
    SN: str | None = Query(None, description="设备 SN（协议字段）"),
    db: Session = Depends(get_db),
):
    """待我审核：当前绑定成员节点为 PENDING 的单据列表（全量）。"""
    return ok(biz_card_agent_service.list_todos(db, _sn(sn, SN)))


@router.get("/mine")
@no_audit
def list_mine(
    sn: str | None = Query(None, description="设备 SN"),
    SN: str | None = Query(None, description="设备 SN（协议字段）"),
    db: Session = Depends(get_db),
):
    """我的提交：审批中全部 + 近 7 天内已通过/已驳回。"""
    return ok(biz_card_agent_service.list_mine(db, _sn(sn, SN)))


@router.get("/detail")
@no_audit
def get_detail(
    bizId: str = Query(..., description="单据 ID"),
    sn: str | None = Query(None, description="设备 SN"),
    SN: str | None = Query(None, description="设备 SN（协议字段）"),
    db: Session = Depends(get_db),
):
    """业务卡片详情（完整审批步骤）。"""
    return ok(biz_card_agent_service.get_detail(db, _sn(sn, SN), bizId))
