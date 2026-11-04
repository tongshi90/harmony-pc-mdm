"""业务卡片 · ② 解析校验并拆表覆盖落库.

落库本身不校验工号是否存在；commit 成功后尽力 MQTT 催拉（失败不影响上报成功）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.biz_card import BizCard, BizCardStep
from app.services import biz_card_notify_service
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as now_local

logger = logging.getLogger("mdm.biz_card")

OVERALL_STATUSES = frozenset({"PENDING", "APPROVED", "REJECTED"})
STEP_STATUSES = frozenset({"APPROVED", "REJECTED", "PENDING", "WAITING"})
CONTENT_MAX_LEN = 200
SOURCE_REPORT = "REPORT"

# 业务校验失败码（与 OpenAPI 响应约定一致）
CODE_VALIDATION = 40001


class BizCardValidationError(Exception):
    """参数/业务校验失败 → 对外 code=40001."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message or "参数校验失败"
        self.code = CODE_VALIDATION


def upsert_biz_card(
    db: Session,
    raw: dict[str, Any],
    *,
    source: str = SOURCE_REPORT,
) -> str:
    """校验整单 JSON，按 bizId 覆盖主表 + 步骤副表。返回 biz_id."""
    data = _normalize_and_validate(raw)
    biz_id = data["biz_id"]

    row = db.query(BizCard).filter(BizCard.biz_id == biz_id).first()
    old_applicant_id = (row.applicant_id if row else None) or None
    old_pending_ids: list[str] = []
    if row is not None:
        old_pending_ids = [
            s.handler_id
            for s in db.query(BizCardStep)
            .filter(BizCardStep.biz_id == biz_id, BizCardStep.status == "PENDING")
            .all()
            if (s.handler_id or "").strip()
        ]

    if row is None:
        row = BizCard(biz_id=biz_id)
        db.add(row)

    row.title = data["title"]
    row.content = data["content"]
    row.applicant_id = data["applicant_id"]
    row.submit_time = data["submit_time"]
    row.overall_status = data["overall_status"]
    row.current_step = data["current_step"]
    row.total_step = data["total_step"]
    row.current_handler_id = data["current_handler_id"]
    row.handle_url = data["handle_url"]
    row.update_time = now_local()
    row.last_source = source or SOURCE_REPORT

    db.query(BizCardStep).filter(BizCardStep.biz_id == biz_id).delete(
        synchronize_session=False
    )
    for step in data["steps"]:
        db.add(
            BizCardStep(
                id=snowflake_id(),
                biz_id=biz_id,
                step=step["step"],
                handler_id=step["handler_id"],
                status=step["status"],
                handle_url=step["handle_url"],
                occur_time=step["occur_time"],
                finish_time=step["finish_time"],
                reject_reason=step["reject_reason"],
            )
        )

    db.commit()
    logger.info(
        "业务卡片覆盖落库 biz_id=%s status=%s steps=%s source=%s",
        biz_id,
        data["overall_status"],
        data["total_step"],
        row.last_source,
    )

    new_pending_ids = [
        s["handler_id"]
        for s in data["steps"]
        if (s.get("status") or "") == "PENDING" and (s.get("handler_id") or "").strip()
    ]
    try:
        biz_card_notify_service.notify_after_upsert(
            db,
            applicant_id=data["applicant_id"],
            new_pending_handler_ids=new_pending_ids,
            old_pending_handler_ids=old_pending_ids,
            old_applicant_id=old_applicant_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("业务卡片 MQTT 催拉异常（已忽略）biz_id=%s", biz_id)

    return biz_id


def _normalize_and_validate(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BizCardValidationError("参数校验失败：请求体须为 JSON 对象")

    biz_id = _req_str(raw, "bizId", max_len=64)
    title = _req_str(raw, "title", max_len=128)
    content = _req_str(raw, "content", max_len=512)
    if len(content) > CONTENT_MAX_LEN:
        raise BizCardValidationError(
            f"参数校验失败：content 不超过 {CONTENT_MAX_LEN} 字"
        )
    applicant_id = _req_str(raw, "applicantId", max_len=64)
    submit_time = _parse_time(
        _req_str(raw, "submitTime", max_len=64), field="submitTime"
    )

    overall = _req_str(raw, "overallStatus", max_len=16).upper()
    if overall not in OVERALL_STATUSES:
        raise BizCardValidationError(
            "参数校验失败：overallStatus 须为 PENDING / APPROVED / REJECTED"
        )

    total_step = _req_int(raw, "totalStep", min_v=1)
    approvals = raw.get("approvals")
    if not isinstance(approvals, list) or not approvals:
        raise BizCardValidationError("参数校验失败：approvals 不能为空")
    if total_step != len(approvals):
        raise BizCardValidationError(
            "参数校验失败：totalStep 须等于 approvals 条数"
        )

    steps = [_validate_step(item, idx) for idx, item in enumerate(approvals)]
    steps.sort(key=lambda x: x["step"])
    expected = list(range(1, total_step + 1))
    actual = [s["step"] for s in steps]
    if actual != expected:
        raise BizCardValidationError(
            "参数校验失败：approvals.step 须从 1 连续递增且无重复"
        )

    current_step_raw = raw.get("currentStep")
    current_handler = _opt_str(raw.get("currentHandlerId"), max_len=64)
    handle_url = _opt_str(raw.get("handleUrl"), max_len=512)

    if overall == "PENDING":
        if current_step_raw is None:
            raise BizCardValidationError(
                "参数校验失败：overallStatus=PENDING 时 currentStep 必填"
            )
        current_step = _as_int(current_step_raw, field="currentStep", min_v=1)
        if current_step > total_step:
            raise BizCardValidationError(
                "参数校验失败：currentStep 不能大于 totalStep"
            )
        if not current_handler:
            raise BizCardValidationError(
                "参数校验失败：overallStatus=PENDING 时 currentHandlerId 必填"
            )
        if not handle_url:
            raise BizCardValidationError(
                "参数校验失败：overallStatus=PENDING 时 handleUrl 必填"
            )
    else:
        # 终态：可保留最后一级；缺省则用 total_step
        if current_step_raw is None:
            current_step = total_step
        else:
            current_step = _as_int(current_step_raw, field="currentStep", min_v=1)
        current_handler = None
        handle_url = None

    return {
        "biz_id": biz_id,
        "title": title,
        "content": content,
        "applicant_id": applicant_id,
        "submit_time": submit_time,
        "overall_status": overall,
        "current_step": current_step,
        "total_step": total_step,
        "current_handler_id": current_handler,
        "handle_url": handle_url,
        "steps": steps,
    }


def _validate_step(item: Any, idx: int) -> dict[str, Any]:
    prefix = f"approvals[{idx}]"
    if not isinstance(item, dict):
        raise BizCardValidationError(f"参数校验失败：{prefix} 须为对象")

    step = _as_int(item.get("step"), field=f"{prefix}.step", min_v=1)
    handler_id = _req_str(item, "handlerId", max_len=64, label=f"{prefix}.handlerId")
    status = _req_str(item, "status", max_len=16, label=f"{prefix}.status").upper()
    if status not in STEP_STATUSES:
        raise BizCardValidationError(
            f"参数校验失败：{prefix}.status 须为 "
            "APPROVED / REJECTED / PENDING / WAITING"
        )

    handle_url = _opt_str(item.get("handleUrl"), max_len=512)
    occur_time = _opt_time(item.get("occurTime"), field=f"{prefix}.occurTime")
    finish_time = _opt_time(item.get("finishTime"), field=f"{prefix}.finishTime")
    reject_reason = _opt_str(item.get("rejectReason"), max_len=512)

    if status == "PENDING":
        if not handle_url:
            raise BizCardValidationError(
                f"参数校验失败：{prefix} status=PENDING 时 handleUrl 必填"
            )
        if occur_time is None:
            raise BizCardValidationError(
                f"参数校验失败：{prefix} status=PENDING 时 occurTime 必填"
            )
    elif status == "APPROVED":
        if finish_time is None:
            raise BizCardValidationError(
                f"参数校验失败：{prefix} status=APPROVED 时 finishTime 必填"
            )
    elif status == "REJECTED":
        if not reject_reason:
            raise BizCardValidationError(
                f"参数校验失败：{prefix} status=REJECTED 时 rejectReason 必填"
            )
        if finish_time is None:
            raise BizCardValidationError(
                f"参数校验失败：{prefix} status=REJECTED 时 finishTime 必填"
            )
    elif status == "WAITING":
        # 未轮到：时间与 handleUrl 可空
        pass

    return {
        "step": step,
        "handler_id": handler_id,
        "status": status,
        "handle_url": handle_url,
        "occur_time": occur_time,
        "finish_time": finish_time,
        "reject_reason": reject_reason,
    }


def _req_str(
    obj: dict[str, Any],
    key: str,
    *,
    max_len: int,
    label: str | None = None,
) -> str:
    label = label or key
    val = obj.get(key)
    if val is None or (isinstance(val, str) and not val.strip()):
        raise BizCardValidationError(f"参数校验失败：缺少 {label}")
    if not isinstance(val, str):
        val = str(val)
    text = val.strip()
    if not text:
        raise BizCardValidationError(f"参数校验失败：缺少 {label}")
    if len(text) > max_len:
        raise BizCardValidationError(
            f"参数校验失败：{label} 长度不能超过 {max_len}"
        )
    return text


def _opt_str(val: Any, *, max_len: int) -> str | None:
    if val is None:
        return None
    if not isinstance(val, str):
        val = str(val)
    text = val.strip()
    if not text:
        return None
    if len(text) > max_len:
        raise BizCardValidationError(
            f"参数校验失败：字段长度不能超过 {max_len}"
        )
    return text


def _req_int(obj: dict[str, Any], key: str, *, min_v: int) -> int:
    return _as_int(obj.get(key), field=key, min_v=min_v)


def _as_int(val: Any, *, field: str, min_v: int) -> int:
    if val is None or (isinstance(val, str) and not val.strip()):
        raise BizCardValidationError(f"参数校验失败：缺少 {field}")
    try:
        num = int(val)
    except (TypeError, ValueError) as exc:
        raise BizCardValidationError(
            f"参数校验失败：{field} 须为整数"
        ) from exc
    if num < min_v:
        raise BizCardValidationError(
            f"参数校验失败：{field} 不能小于 {min_v}"
        )
    return num


def _parse_time(text: str, *, field: str) -> datetime:
    try:
        # 支持尾部 Z
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BizCardValidationError(
            f"参数校验失败：{field} 须为 ISO8601 时间"
        ) from exc
    # 库表存本地朴素时间：有时区则转本地墙钟再去 tzinfo
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _opt_time(val: Any, *, field: str) -> datetime | None:
    if val is None:
        return None
    if not isinstance(val, str) or not val.strip():
        return None
    return _parse_time(val.strip(), field=field)
