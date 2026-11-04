"""业务卡片 · 落库后 MQTT 催拉（与段落 A 落库解耦；失败不影响上报成功）.

固定 payload：
- 我的提交有更新 → {"type":"BIZ_CARD_PULL","bizType":"mySubmission"}
- 待我审核有更新 → {"type":"BIZ_CARD_PULL","bizType":"pendingReview"}

工号不存在 / 未绑定设备 → 该路静默跳过，其它人照常下发。
"""

from __future__ import annotations

import json
import logging
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.department import SysMember
from app.models.device import Device
from app.mqtt import publish_mqtt

logger = logging.getLogger("mdm.biz_card")

BIZ_TYPE_MINE = "mySubmission"
BIZ_TYPE_TODO = "pendingReview"

_PAYLOAD_MINE = json.dumps(
    {"type": "BIZ_CARD_PULL", "bizType": BIZ_TYPE_MINE},
    ensure_ascii=False,
    separators=(",", ":"),
)
_PAYLOAD_TODO = json.dumps(
    {"type": "BIZ_CARD_PULL", "bizType": BIZ_TYPE_TODO},
    ensure_ascii=False,
    separators=(",", ":"),
)


def notify_after_upsert(
    db: Session,
    *,
    applicant_id: str,
    new_pending_handler_ids: Iterable[str],
    old_pending_handler_ids: Iterable[str] | None = None,
    old_applicant_id: str | None = None,
) -> None:
    """按角色分别催拉；互不影响."""
    # 我的提交：当前提交人；若提交人变更则旧提交人也刷一次
    mine_emps: set[str] = set()
    for eid in (applicant_id, old_applicant_id):
        e = (eid or "").strip()
        if e:
            mine_emps.add(e)

    # 待我审核：新 PENDING ∪ 旧 PENDING（含已不再待审的人，便于端侧列表去掉该单）
    todo_emps: set[str] = set()
    for eid in list(new_pending_handler_ids or []) + list(old_pending_handler_ids or []):
        e = (eid or "").strip()
        if e:
            todo_emps.add(e)

    for eid in mine_emps:
        _publish_for_employee(db, eid, biz_type=BIZ_TYPE_MINE, payload=_PAYLOAD_MINE)
    for eid in todo_emps:
        _publish_for_employee(db, eid, biz_type=BIZ_TYPE_TODO, payload=_PAYLOAD_TODO)


def _publish_for_employee(
    db: Session,
    employee_id: str,
    *,
    biz_type: str,
    payload: str,
) -> None:
    sn = _bound_sn_by_employee_id(db, employee_id)
    if not sn:
        logger.info(
            "业务卡片 MQTT 跳过：无绑定设备 employee_id=%s bizType=%s",
            employee_id,
            biz_type,
        )
        return
    try:
        publish_mqtt(sn=sn, message=payload, qos=1)
        logger.info(
            "业务卡片 MQTT 已发 sn=%s employee_id=%s bizType=%s",
            sn,
            employee_id,
            biz_type,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "业务卡片 MQTT 失败 sn=%s employee_id=%s bizType=%s: %s",
            sn,
            employee_id,
            biz_type,
            exc,
        )


def _bound_sn_by_employee_id(db: Session, employee_id: str) -> str | None:
    eid = (employee_id or "").strip()
    if not eid:
        return None
    member = (
        db.query(SysMember)
        .filter(SysMember.employee_id == eid, SysMember.is_delete == 0)
        .first()
    )
    if not member:
        return None
    device = (
        db.query(Device)
        .filter(
            Device.member_id == member.id,
            Device.bind_status == 1,
        )
        .first()
    )
    if not device or not (device.sn or "").strip():
        return None
    return device.sn.strip()
