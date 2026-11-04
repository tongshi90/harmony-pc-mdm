"""设备侧 · 业务卡片拉取（/api/biz-card/*）.

提醒定位：
- 待我审核：仅节点 PENDING
- 我的提交：审批中全部 + 近 N 天终态（已通过/已驳回）
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.biz_card import BizCard, BizCardStep
from app.models.department import SysMember
from app.models.device import Device
from app.services.device_biz_card_service import (
    OVERALL_LABEL,
    STEP_LABEL,
    _fmt_dt,
    _name_map,
)
from app.utils.timeutil import now as local_now

# 我的提交：终态保留天数
MINE_TERMINAL_DAYS = 7


def _resolve_bound_member(db: Session, sn: str) -> tuple[Device | None, SysMember | None]:
    device_sn = (sn or "").strip()
    if not device_sn:
        return None, None
    device = db.query(Device).filter(Device.sn == device_sn).first()
    if not device:
        return None, None
    if device.member_id is None or int(device.bind_status or 0) != 1:
        return device, None
    member = (
        db.query(SysMember)
        .filter(SysMember.id == device.member_id, SysMember.is_delete == 0)
        .first()
    )
    return device, member


def _list_item(
    card: BizCard,
    *,
    applicant_name: str | None,
    handle_url: str | None = None,
) -> dict:
    return {
        "bizId": card.biz_id,
        "title": card.title,
        "content": card.content,
        "applicantId": card.applicant_id,
        "applicantName": applicant_name or "",
        "submitTime": _fmt_dt(card.submit_time),
        "overallStatus": card.overall_status,
        "overallStatusLabel": OVERALL_LABEL.get(
            card.overall_status or "", card.overall_status or ""
        ),
        "currentStep": card.current_step,
        "totalStep": card.total_step,
        "handleUrl": handle_url if handle_url is not None else card.handle_url,
        "updateTime": _fmt_dt(card.update_time),
    }


def list_todos(db: Session, sn: str) -> dict:
    """待我审核：当前成员节点 PENDING 的单据全量列表."""
    _, member = _resolve_bound_member(db, sn)
    if not member:
        return {"list": []}

    me = (member.employee_id or "").strip()
    if not me:
        return {"list": []}

    pairs = (
        db.query(BizCardStep, BizCard)
        .join(BizCard, BizCard.biz_id == BizCardStep.biz_id)
        .filter(
            BizCardStep.handler_id == me,
            BizCardStep.status == "PENDING",
        )
        .order_by(BizCardStep.occur_time.desc(), BizCardStep.biz_id.desc())
        .all()
    )
    names = _name_map(db, {card.applicant_id for _, card in pairs})
    return {
        "list": [
            _list_item(
                card,
                applicant_name=names.get(card.applicant_id),
                handle_url=step.handle_url or card.handle_url,
            )
            for step, card in pairs
        ]
    }


def list_mine(db: Session, sn: str, *, terminal_days: int = MINE_TERMINAL_DAYS) -> dict:
    """我的提交：PENDING 全部 + 近 terminal_days 天内的 APPROVED/REJECTED."""
    _, member = _resolve_bound_member(db, sn)
    if not member:
        return {"list": []}

    me = (member.employee_id or "").strip()
    if not me:
        return {"list": []}

    days = max(1, int(terminal_days or MINE_TERMINAL_DAYS))
    since = local_now() - timedelta(days=days)
    rows = (
        db.query(BizCard)
        .filter(
            BizCard.applicant_id == me,
            or_(
                BizCard.overall_status == "PENDING",
                and_(
                    BizCard.overall_status.in_(("APPROVED", "REJECTED")),
                    BizCard.update_time >= since,
                ),
            ),
        )
        .order_by(BizCard.submit_time.desc(), BizCard.biz_id.desc())
        .all()
    )
    names = _name_map(db, {me})
    my_name = names.get(me, member.name or "")
    return {
        "list": [
            _list_item(card, applicant_name=my_name, handle_url=card.handle_url)
            for card in rows
        ]
    }


def get_detail(db: Session, sn: str, biz_id: str) -> dict:
    """单条详情（完整步骤）."""
    device_sn = (sn or "").strip()
    if not device_sn:
        raise HTTPException(status_code=400, detail="请提供设备 SN")
    bid = (biz_id or "").strip()
    if not bid:
        raise HTTPException(status_code=400, detail="请提供 bizId")

    _, member = _resolve_bound_member(db, device_sn)
    if not member:
        raise HTTPException(status_code=400, detail="设备未绑定成员")

    me = (member.employee_id or "").strip()
    card = db.query(BizCard).filter(BizCard.biz_id == bid).first()
    if not card:
        raise HTTPException(status_code=404, detail="业务卡片不存在")

    steps = (
        db.query(BizCardStep)
        .filter(BizCardStep.biz_id == bid)
        .order_by(BizCardStep.step.asc())
        .all()
    )
    related = card.applicant_id == me or any(s.handler_id == me for s in steps)
    if not related:
        raise HTTPException(status_code=404, detail="业务卡片不存在或不属于该成员")

    names = _name_map(
        db, {card.applicant_id, *(s.handler_id for s in steps), card.current_handler_id or ""}
    )
    my_pending = next(
        (s for s in steps if s.handler_id == me and s.status == "PENDING"),
        None,
    )
    overall_rejected = (card.overall_status or "") == "REJECTED"

    step_out = []
    for s in steps:
        skipped = overall_rejected and (s.status or "") == "WAITING"
        label = (
            "未进行"
            if skipped
            else STEP_LABEL.get(s.status or "", s.status or "")
        )
        step_out.append(
            {
                "step": s.step,
                "handlerId": s.handler_id,
                "handlerName": names.get(s.handler_id, ""),
                "status": s.status,
                "statusLabel": label,
                "finishTime": None if skipped else _fmt_dt(s.finish_time),
                "rejectReason": s.reject_reason
                if (s.status or "") == "REJECTED"
                else None,
            }
        )

    return {
        "bizId": card.biz_id,
        "title": card.title,
        "content": card.content,
        "applicantId": card.applicant_id,
        "applicantName": names.get(card.applicant_id, ""),
        "submitTime": _fmt_dt(card.submit_time),
        "overallStatus": card.overall_status,
        "overallStatusLabel": OVERALL_LABEL.get(
            card.overall_status or "", card.overall_status or ""
        ),
        "currentStep": card.current_step,
        "totalStep": card.total_step,
        "currentHandlerId": card.current_handler_id,
        "currentHandlerName": names.get(card.current_handler_id or "", ""),
        "handleUrl": (my_pending.handle_url if my_pending else None) or card.handle_url,
        "updateTime": _fmt_dt(card.update_time),
        "steps": step_out,
    }
