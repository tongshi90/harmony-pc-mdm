"""设备详情 · 业务卡片查询（按绑定成员工号过滤）.

- 我的提交：applicant_id = 工号（含审批中 / 已通过 / 已驳回）
- 待我审核：步骤表 handler_id = 工号 且 status = PENDING（仅当前轮到本人）
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.biz_card import BizCard, BizCardStep
from app.models.department import SysMember
from app.models.device import Device

KIND_MINE = "mine"
KIND_TODO = "todo"
KIND_LABEL = {
    KIND_MINE: "我的提交",
    KIND_TODO: "待我审核",
}
OVERALL_LABEL = {
    "PENDING": "审批中",
    "APPROVED": "已通过",
    "REJECTED": "已驳回",
}
STEP_LABEL = {
    "APPROVED": "已通过",
    "REJECTED": "已驳回",
    "PENDING": "待审批",
    "WAITING": "等待中",
}


def _get_device(db: Session, sn: str) -> Device:
    device_sn = (sn or "").strip()
    if not device_sn:
        raise HTTPException(status_code=400, detail="请提供设备 SN")
    row = db.query(Device).filter(Device.sn == device_sn).first()
    if not row:
        raise HTTPException(status_code=404, detail="设备不存在")
    return row


def _bound_member(db: Session, device: Device) -> SysMember | None:
    if device.member_id is None or int(device.bind_status or 0) != 1:
        return None
    return (
        db.query(SysMember)
        .filter(SysMember.id == device.member_id, SysMember.is_delete == 0)
        .first()
    )


def _fmt_dt(val: datetime | None) -> str | None:
    if val is None:
        return None
    return val.strftime("%Y-%m-%d %H:%M:%S")


def _name_map(db: Session, employee_ids: set[str]) -> dict[str, str]:
    ids = {x for x in employee_ids if x}
    if not ids:
        return {}
    rows = (
        db.query(SysMember.employee_id, SysMember.name)
        .filter(SysMember.employee_id.in_(ids), SysMember.is_delete == 0)
        .all()
    )
    return {eid: name for eid, name in rows if eid}


def _card_list_item(
    card: BizCard,
    *,
    kind: str,
    applicant_name: str | None,
    step_handle_url: str | None = None,
    step_occur_time: datetime | None = None,
) -> dict:
    return {
        "bizId": card.biz_id,
        "kind": kind,
        "kindLabel": KIND_LABEL.get(kind, kind),
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
        "currentHandlerId": card.current_handler_id,
        "handleUrl": step_handle_url or card.handle_url,
        "todoOccurTime": _fmt_dt(step_occur_time) if kind == KIND_TODO else None,
        "updateTime": _fmt_dt(card.update_time),
    }


def list_device_biz_cards(
    db: Session,
    sn: str,
    *,
    kind: str,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """按设备绑定成员列出业务卡片."""
    kind = (kind or "").strip().lower()
    if kind not in (KIND_MINE, KIND_TODO):
        raise HTTPException(
            status_code=400, detail="kind 须为 mine（我的提交）或 todo（待我审核）"
        )

    device = _get_device(db, sn)
    member = _bound_member(db, device)
    if not member:
        return {
            "bound": False,
            "employeeId": None,
            "memberName": None,
            "kind": kind,
            "kindLabel": KIND_LABEL[kind],
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "message": "设备未绑定成员，无业务卡片",
        }

    me = (member.employee_id or "").strip()
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), 100))

    if kind == KIND_MINE:
        q = db.query(BizCard).filter(BizCard.applicant_id == me)
        total = q.count()
        rows = (
            q.order_by(BizCard.submit_time.desc(), BizCard.biz_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        names = _name_map(db, {me, *(r.applicant_id for r in rows)})
        items = [
            _card_list_item(
                r,
                kind=KIND_MINE,
                applicant_name=names.get(r.applicant_id),
            )
            for r in rows
        ]
    else:
        q = (
            db.query(BizCardStep, BizCard)
            .join(BizCard, BizCard.biz_id == BizCardStep.biz_id)
            .filter(
                BizCardStep.handler_id == me,
                BizCardStep.status == "PENDING",
            )
        )
        total = q.count()
        pairs = (
            q.order_by(
                BizCardStep.occur_time.desc(),
                BizCardStep.biz_id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        applicant_ids = {card.applicant_id for _, card in pairs}
        names = _name_map(db, applicant_ids)
        items = [
            _card_list_item(
                card,
                kind=KIND_TODO,
                applicant_name=names.get(card.applicant_id),
                step_handle_url=step.handle_url,
                step_occur_time=step.occur_time,
            )
            for step, card in pairs
        ]

    return {
        "bound": True,
        "employeeId": me,
        "memberName": member.name,
        "kind": kind,
        "kindLabel": KIND_LABEL[kind],
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "message": "",
    }


def get_device_biz_card_detail(db: Session, sn: str, biz_id: str) -> dict:
    """单条详情：主表 + 全步骤；须与当前绑定成员相关（提交人或任一步骤审批人）."""
    device = _get_device(db, sn)
    member = _bound_member(db, device)
    if not member:
        raise HTTPException(status_code=400, detail="设备未绑定成员")

    me = (member.employee_id or "").strip()
    bid = (biz_id or "").strip()
    if not bid:
        raise HTTPException(status_code=400, detail="请提供 bizId")

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

    emp_ids = {card.applicant_id, *(s.handler_id for s in steps)}
    names = _name_map(db, emp_ids)

    my_pending = next(
        (s for s in steps if s.handler_id == me and s.status == "PENDING"),
        None,
    )
    is_applicant = card.applicant_id == me
    is_my_pending = my_pending is not None
    if is_my_pending and not is_applicant:
        view_kind = KIND_TODO
    elif is_applicant:
        view_kind = KIND_MINE
    else:
        view_kind = KIND_TODO if is_my_pending else KIND_MINE

    return {
        "bound": True,
        "employeeId": me,
        "memberName": member.name,
        "kind": view_kind,
        "kindLabel": KIND_LABEL[view_kind],
        "isApplicant": is_applicant,
        "isMyPending": is_my_pending,
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
        "steps": [
            {
                "step": s.step,
                "handlerId": s.handler_id,
                "handlerName": names.get(s.handler_id, ""),
                "status": s.status,
                "statusLabel": STEP_LABEL.get(s.status or "", s.status or ""),
                "handleUrl": s.handle_url,
                "occurTime": _fmt_dt(s.occur_time),
                "finishTime": _fmt_dt(s.finish_time),
                "rejectReason": s.reject_reason,
            }
            for s in steps
        ],
    }
