"""策略下发：任务配置落库、MQTT 通知、预期快照；设备对齐看快照匹配.

说明：一次 pull 可能覆盖多次下发配置，故不以「设备任务状态机」追踪成败。
终端侧对齐状态 = 预期快照 vs 当前快照（匹配 / 不匹配）。
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.enums.policy_change_op import (
    ALL as POLICY_OP_TYPES,
    DISPATCH,
    LABELS_ZH as OP_TYPE_LABELS,
    resolve_policy_timing,
)
from app.models.department import SysDepartment, SysMember
from app.models.device import Device
from app.models.policy_task import PolicyDeviceTask, PolicyTask, PolicyTaskItem
from app.models.user import User
from app.mqtt import publish_mqtt, publish_mqtt_many
from app.services import device_snapshot_service
from app.services.device_online_sync_service import sync_device_online_status
from app.utils.policy_summary import (
    aggregate_policy_summaries,
    build_policy_item_summary,
    make_app_name_resolver,
)
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

logger = logging.getLogger("mdm.policy.dispatch")

MQTT_STRATEGY_PULL_PAYLOAD = '{"type":"STRATEGY_PULL"}'
MQTT_DEVICE_UNBINDING_PAYLOAD = '{"type":"DEVICE_UNBINDING"}'
ALLOWED_WAIT_HOURS = frozenset({1, 2, 4, 8, 12, 24})


def _fmt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data]


def _parse_param(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dumps_param(param: dict[str, Any] | None) -> str:
    return json.dumps(param or {}, ensure_ascii=False, separators=(",", ":"))


def _parse_id(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"无效的 ID：{value}") from exc


def _normalize_items(raw_items: list | None) -> list[tuple[str, dict[str, Any], int]]:
    by_code: dict[str, tuple[str, dict[str, Any], int]] = {}
    for idx, it in enumerate(raw_items or []):
        code = (getattr(it, "policy_code", None) or "").strip()
        if not code:
            raise HTTPException(status_code=400, detail="策略项 policy_code 不能为空")
        if code == "PASSWORD_POLICY":
            code = "PSW_MANAGEMENT"
        param = getattr(it, "param", None) or {}
        if not isinstance(param, dict):
            raise HTTPException(status_code=400, detail=f"策略项 {code} 的 param 须为对象")
        sort = int(getattr(it, "sort", idx) or idx)
        by_code[code] = (code, param, sort)
    if not by_code:
        raise HTTPException(status_code=400, detail="请至少配置一条策略项")
    ordered = sorted(by_code.values(), key=lambda x: (x[2], x[0]))
    return [(code, param, i + 1) for i, (code, param, _) in enumerate(ordered)]


def _collect_dept_ids_recursive(db: Session, root_ids: list[int]) -> set[int]:
    if not root_ids:
        return set()
    all_rows = db.query(SysDepartment.id, SysDepartment.parent_id).all()
    children: dict[int | None, list[int]] = {}
    for did, pid in all_rows:
        children.setdefault(pid, []).append(did)
    result: set[int] = set()
    stack = list(root_ids)
    while stack:
        cur = stack.pop()
        if cur in result:
            continue
        result.add(cur)
        stack.extend(children.get(cur, []))
    return result


def _devices_for_member_ids(
    db: Session, member_ids: list[int]
) -> list[tuple[Device, SysMember | None]]:
    if not member_ids:
        return []
    rows = (
        db.query(Device, SysMember)
        .outerjoin(SysMember, SysMember.id == Device.member_id)
        .filter(Device.member_id.in_(member_ids))
        .order_by(Device.sn.asc())
        .all()
    )
    seen: set[str] = set()
    out: list[tuple[Device, SysMember | None]] = []
    for device, member in rows:
        sn = (device.sn or "").strip()
        if not sn or sn in seen:
            continue
        seen.add(sn)
        out.append((device, member))
    return out


def _resolve_targets(
    db: Session, *, target_type: str, group_ids: list[str], member_ids: list[str]
) -> tuple[list[tuple[Device, SysMember | None]], str, list[str]]:
    """解析目标设备.

    返回 (设备列表, target_desc, group_id_strs)。
    group_id_strs 仅按组选择时有值；手动选人时为 []（人员明细只落 t_policy_device_task）。
    """
    if target_type == "group":
        raw_ids = [_parse_id(x) for x in (group_ids or [])]
        ids = [x for x in raw_ids if x is not None]
        if not ids:
            raise HTTPException(status_code=400, detail="请选择成员分组")
        depts = (
            db.query(SysDepartment)
            .filter(SysDepartment.id.in_(ids))
            .order_by(SysDepartment.path.asc())
            .all()
        )
        if len(depts) != len(set(ids)):
            raise HTTPException(status_code=400, detail="部分成员分组不存在")
        scope_ids = _collect_dept_ids_recursive(db, ids)
        members = (
            db.query(SysMember)
            .filter(
                SysMember.department_id.in_(scope_ids),
                SysMember.is_delete == 0,
            )
            .all()
        )
        devices = _devices_for_member_ids(db, [m.id for m in members])
        names = [d.path or d.name for d in depts[:3]]
        extra = f" 等 {len(depts)} 个" if len(depts) > 3 else ""
        label = "、".join(names) + extra if names else "未命名分组"
        desc = f"分组 · {label}（含子组）· {len(members)} 人"
        return devices, desc, [str(i) for i in ids]

    if target_type == "member":
        raw_ids = [_parse_id(x) for x in (member_ids or [])]
        ids = [x for x in raw_ids if x is not None]
        if not ids:
            raise HTTPException(status_code=400, detail="请选择人员")
        members = (
            db.query(SysMember)
            .filter(SysMember.id.in_(ids), SysMember.is_delete == 0)
            .all()
        )
        if len(members) != len(set(ids)):
            raise HTTPException(status_code=400, detail="部分人员不存在或已删除")
        devices = _devices_for_member_ids(db, ids)
        desc = f"手动选人 · {len(members)} 人"
        # 任务头不存人员 ID 列表（人多不合适）；明细在 device_task
        return devices, desc, []

    raise HTTPException(status_code=400, detail="target_type 须为 group 或 member")


def _items_out(db: Session, task_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(PolicyTaskItem)
        .filter(PolicyTaskItem.task_id == task_id)
        .order_by(PolicyTaskItem.sort_order.asc(), PolicyTaskItem.id.asc())
        .all()
    )
    return [
        {
            "id": str(r.id),
            "policy_code": r.policy_code,
            "param": _parse_param(r.param_json),
            "summary": (r.summary or "").strip()
            or build_policy_item_summary(r.policy_code, _parse_param(r.param_json)),
            "sort": int(r.sort_order or 0),
        }
        for r in rows
    ]


def _task_out(db: Session, row: PolicyTask, *, detail: bool = False) -> dict[str, Any]:
    group_ids = _parse_json_list(row.target_json)
    op_type = (row.op_type or DISPATCH).strip() or DISPATCH
    data: dict[str, Any] = {
        "id": str(row.id),
        "op_type": op_type,
        "op_type_label": OP_TYPE_LABELS.get(op_type, op_type),
        "name": row.name,
        "policy_level": row.policy_level,
        "wait_hours": row.wait_hours,
        "deadline": _fmt(row.deadline_at),
        # 兼容前端：有分组 ID 视为按组；否则为手动选人
        "target_type": "group" if group_ids else "member",
        "group_ids": group_ids,
        "target_ids": group_ids,
        "target_desc": row.target_desc or "",
        "source_id": str(row.source_id) if row.source_id else None,
        "ext": _parse_param(row.ext_json) if getattr(row, "ext_json", None) else {},
        "creator_id": str(row.creator_id) if row.creator_id else None,
        "creator": row.creator_name or "",
        "targets": int(row.target_count or 0),
        "item_count": 0,
        "create_time": _fmt(row.create_time),
        "update_time": _fmt(row.update_time),
    }
    stored = (row.policy_summary or "").strip()
    if detail:
        items = _items_out(db, row.id)
        data["item_count"] = len(items)
        data["items"] = items
        data["policy_summary"] = stored or aggregate_policy_summaries(
            [it.get("summary") or "" for it in items]
        )
        data["devices"] = _task_targets_out(db, row.id)
    else:
        if stored:
            data["policy_summary"] = stored
        else:
            items = _items_out(db, row.id)
            data["item_count"] = len(items)
            data["policy_summary"] = aggregate_policy_summaries(
                [it.get("summary") or "" for it in items]
            )
    return data


def _task_targets_out(db: Session, task_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(PolicyDeviceTask)
        .filter(PolicyDeviceTask.task_id == task_id)
        .order_by(PolicyDeviceTask.device_sn.asc())
        .all()
    )
    return [
        {
            "id": str(r.id),
            "device_id": str(r.device_id),
            "sn": r.device_sn,
            "member_id": str(r.member_id) if r.member_id else None,
            "member_name": r.member_name or "",
            "employee_id": r.employee_id or "",
            "department_id": str(r.department_id) if r.department_id else None,
            "department_path": r.department_path or "",
        }
        for r in rows
    ]


def _online_label(status: int | None) -> str:
    return {1: "online", 2: "offline", 3: "lost"}.get(int(status or 2), "offline")


def _parse_query_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD") from exc


def list_tasks(
    db: Session,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    op_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    q = db.query(PolicyTask)
    # 策略记录页默认展示全部来源；传具体 op_type 时可筛选
    ot = (op_type or "").strip()
    if ot and ot.lower() != "all":
        if ot not in POLICY_OP_TYPES:
            raise HTTPException(status_code=400, detail="不支持的策略来源")
        q = q.filter(PolicyTask.op_type == ot)

    # 关键词仅模糊匹配任务名、目标范围（不含 ID / 摘要 / 创建人）
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            or_(
                PolicyTask.name.like(like),
                PolicyTask.target_desc.like(like),
            )
        )

    start = _parse_query_date(start_date)
    end = _parse_query_date(end_date)
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    if start:
        q = q.filter(PolicyTask.create_time >= datetime.combine(start, time.min))
    if end:
        # 结束日按整天计入（含当天 23:59:59）
        q = q.filter(
            PolicyTask.create_time < datetime.combine(end + timedelta(days=1), time.min)
        )

    total = q.count()
    rows = (
        q.order_by(PolicyTask.create_time.desc(), PolicyTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_task_out(db, r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_task(db: Session, task_id: int) -> dict:
    row = db.query(PolicyTask).filter(PolicyTask.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="下发任务不存在")
    return _task_out(db, row, detail=True)


def list_task_devices(
    db: Session,
    task_id: int,
    *,
    keyword: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """兼容旧接口：返回任务目标设备清单（无执行状态）."""
    task = db.query(PolicyTask).filter(PolicyTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="下发任务不存在")
    q = db.query(PolicyDeviceTask).filter(PolicyDeviceTask.task_id == task_id)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            or_(
                PolicyDeviceTask.device_sn.like(like),
                PolicyDeviceTask.member_name.like(like),
            )
        )
    total = q.count()
    rows = (
        q.order_by(PolicyDeviceTask.device_sn.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "sn": r.device_sn,
                "member_name": r.member_name or "",
                "member_id": str(r.member_id) if r.member_id else None,
                "employee_id": r.employee_id or "",
                "department_path": r.department_path or "",
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def list_device_strategy_sync(
    db: Session,
    *,
    keyword: str | None = None,
    match: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """终端策略对齐明细：匹配 / 不匹配（预期 vs 当前快照）."""
    q = db.query(Device)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.outerjoin(SysMember, SysMember.id == Device.member_id).filter(
            or_(
                Device.sn.like(like),
                Device.device_name.like(like),
                SysMember.name.like(like),
                SysMember.employee_id.like(like),
            )
        )
    devices = q.order_by(Device.sn.asc()).all()

    match_filter = (match or "").strip().lower()
    items_all: list[dict[str, Any]] = []
    for device in devices:
        sn = (device.sn or "").strip()
        if not sn:
            continue
        cmp = device_snapshot_service.get_device_snapshot_compare(db, sn)
        consistent = bool(cmp.get("consistent"))
        sync_status = "matched" if consistent else "mismatched"
        if match_filter in ("matched", "mismatched") and sync_status != match_filter:
            continue
        member = None
        dept = None
        if device.member_id:
            member = (
                db.query(SysMember)
                .filter(SysMember.id == device.member_id, SysMember.is_delete == 0)
                .first()
            )
            if member:
                dept = (
                    db.query(SysDepartment)
                    .filter(SysDepartment.id == member.department_id)
                    .first()
                )
        items_all.append(
            {
                "id": str(device.id),
                "sn": sn,
                "device_name": device.device_name or "",
                "model": device.model or "",
                "online_status": _online_label(device.status),
                "online_time": _fmt(device.online_time),
                "member_name": member.name if member else "",
                "employee_id": member.employee_id if member else "",
                "department_path": (dept.path if dept else "") or "",
                "sync_status": sync_status,
                "diff_count": len(cmp.get("diffs") or []),
                "update_time": _fmt(device.update_time),
            }
        )

    total = len(items_all)
    start = max(0, (page - 1) * page_size)
    page_items = items_all[start : start + page_size]
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "matched": sum(1 for x in items_all if x["sync_status"] == "matched"),
        "mismatched": sum(1 for x in items_all if x["sync_status"] == "mismatched"),
    }


def list_target_members(
    db: Session, keyword: str | None = None, page: int = 1, page_size: int = 50
) -> dict:
    device_counts = (
        db.query(Device.member_id, func.count(Device.id).label("cnt"))
        .filter(Device.member_id.isnot(None))
        .group_by(Device.member_id)
        .subquery()
    )
    q = (
        db.query(SysMember, SysDepartment, device_counts.c.cnt)
        .join(device_counts, device_counts.c.member_id == SysMember.id)
        .outerjoin(SysDepartment, SysDepartment.id == SysMember.department_id)
        .filter(SysMember.is_delete == 0)
    )
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            or_(
                SysMember.name.like(like),
                SysMember.employee_id.like(like),
                SysMember.account.like(like),
            )
        )
    total = q.count()
    rows = (
        q.order_by(SysMember.employee_id.asc(), SysMember.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for member, dept, cnt in rows:
        items.append(
            {
                "id": str(member.id),
                "name": member.name,
                "employee_id": member.employee_id,
                "account": member.account,
                "department_id": str(member.department_id),
                "department_path": (dept.path if dept else "")
                or (dept.name if dept else ""),
                "department_name": dept.name if dept else "",
                "device_count": int(cnt or 0),
            }
        )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _merge_task_ext(db: Session, task_id: int, patch: dict[str, Any]) -> None:
    """合并写入任务 ext_json（后台执行进度等）."""
    row = db.query(PolicyTask).filter(PolicyTask.id == task_id).first()
    if not row:
        return
    cur = _parse_param(row.ext_json) if row.ext_json else {}
    if not isinstance(cur, dict):
        cur = {}
    cur.update(patch or {})
    row.ext_json = _dumps_param(cur)
    row.update_time = local_now()


def create_task(db: Session, data, creator: User | None) -> dict:
    """同步：校验并创建任务头 + 策略项 + 目标设备明细；快照与 MQTT 由后台执行."""
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写任务名称")

    # 策略下发：完全按前端选择
    level = (data.policy_level or "normal").strip()
    if level not in ("normal", "urgent"):
        raise HTTPException(status_code=400, detail="策略类型无效")

    ts = local_now()
    raw_wait = data.wait_hours if level == "normal" else None
    if level == "normal":
        hours = raw_wait if raw_wait is not None else 4
        try:
            hours = int(hours)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="最多等待时间无效") from exc
        if hours not in ALLOWED_WAIT_HOURS:
            raise HTTPException(status_code=400, detail="最多等待时间不在可选范围内")
        raw_wait = hours

    level, wait_hours, deadline_at = resolve_policy_timing(
        op_type=DISPATCH,
        policy_level=level,
        wait_hours=raw_wait,
        now=ts,
    )

    items_norm = _normalize_items(data.items)
    devices, target_desc, group_id_strs = _resolve_targets(
        db,
        target_type=data.target_type,
        group_ids=list(data.group_ids or []),
        member_ids=list(data.member_ids or []),
    )
    if not devices:
        raise HTTPException(status_code=400, detail="所选范围内无可用设备")

    task_id = snowflake_id()
    creator_id = creator.id if creator else None
    creator_name = ""
    if creator:
        creator_name = (creator.name or creator.username or "").strip()

    resolve = make_app_name_resolver(db)
    item_summaries: list[str] = []
    for code, param, _sort in items_norm:
        item_summaries.append(
            build_policy_item_summary(code, param, resolve_app_name=resolve)
        )

    task = PolicyTask(
        id=task_id,
        op_type=DISPATCH,
        name=name,
        policy_level=level,
        wait_hours=wait_hours,
        deadline_at=deadline_at,
        target_json=json.dumps(group_id_strs, ensure_ascii=False),
        target_desc=target_desc,
        source_id=None,
        ext_json=_dumps_param({"apply_status": "pending"}),
        creator_id=creator_id,
        creator_name=creator_name or None,
        target_count=len(devices),
        policy_summary=aggregate_policy_summaries(item_summaries),
        create_time=ts,
        update_time=ts,
    )
    db.add(task)

    for (code, param, sort), summary in zip(items_norm, item_summaries):
        db.add(
            PolicyTaskItem(
                id=snowflake_id(),
                task_id=task_id,
                policy_code=code,
                param_json=_dumps_param(param),
                summary=summary,
                sort_order=sort,
                create_time=ts,
                update_time=ts,
            )
        )

    dept_ids = {
        int(m.department_id)
        for _d, m in devices
        if m is not None and m.department_id is not None
    }
    dept_map: dict[int, SysDepartment] = {}
    if dept_ids:
        for d in db.query(SysDepartment).filter(SysDepartment.id.in_(dept_ids)).all():
            dept_map[int(d.id)] = d

    for device, member in devices:
        dept = None
        if member is not None and member.department_id is not None:
            dept = dept_map.get(int(member.department_id))
        db.add(
            PolicyDeviceTask(
                id=snowflake_id(),
                task_id=task_id,
                device_id=device.id,
                device_sn=device.sn,
                member_id=member.id if member else device.member_id,
                member_name=(member.name if member else None),
                employee_id=(member.employee_id if member else None),
                department_id=(member.department_id if member else None),
                department_path=(
                    (dept.path if dept else None) or (dept.name if dept else None)
                ),
                create_time=ts,
                update_time=ts,
            )
        )

    db.commit()
    out = get_task(db, task_id)
    out["accepted"] = True
    out["message"] = "策略任务已创建，正在后台下发，请稍后查看执行结果"
    return out


def apply_dispatch_task_background(task_id: int | str) -> None:
    """后台：整批写入预期快照并一次 commit，再并行 MQTT STRATEGY_PULL."""
    try:
        tid = int(task_id)
    except (TypeError, ValueError):
        logger.error("策略下发后台任务无效 task_id=%s", task_id)
        return

    db = SessionLocal()
    try:
        task = db.query(PolicyTask).filter(PolicyTask.id == tid).first()
        if not task:
            logger.error("策略下发后台任务不存在 task_id=%s", tid)
            return

        _merge_task_ext(db, tid, {"apply_status": "applying"})
        db.commit()

        items = (
            db.query(PolicyTaskItem)
            .filter(PolicyTaskItem.task_id == tid)
            .order_by(PolicyTaskItem.sort_order.asc(), PolicyTaskItem.id.asc())
            .all()
        )
        items_norm = [
            (r.policy_code, _parse_param(r.param_json), int(r.sort_order or 0))
            for r in items
        ]
        device_rows = (
            db.query(PolicyDeviceTask)
            .filter(PolicyDeviceTask.task_id == tid)
            .order_by(PolicyDeviceTask.id.asc())
            .all()
        )

        snapshot_failed = 0
        notify_sns: list[str] = []
        for drow in device_rows:
            sn = (drow.device_sn or "").strip()
            if not sn:
                snapshot_failed += 1
                continue
            try:
                with db.begin_nested():
                    for code, param, _sort in items_norm:
                        device_snapshot_service.upsert_expected(
                            db,
                            device_sn=sn,
                            policy_code=code,
                            param=param,
                            commit=False,
                        )
                    device_snapshot_service.refresh_device_compliance(
                        db, sn, commit=False
                    )
                notify_sns.append(sn)
            except Exception:
                snapshot_failed += 1
                logger.exception("策略下发写预期快照失败 sn=%s task=%s", sn, tid)

        # 整批快照一次提交，再通知（保证拉取到的已是新预期）
        db.commit()

        sync = sync_device_online_status()
        if sync.ok:
            online_set: set[str] | None = {
                str(x).strip() for x in sync.online_sns if str(x).strip()
            }
        else:
            online_set = None
            logger.warning(
                "策略下发后台在线同步失败，降级全量尝试通知: %s", sync.message
            )

        skipped_offline = 0
        mqtt_targets: list[str] = []
        for sn in notify_sns:
            if online_set is not None and sn not in online_set:
                skipped_offline += 1
                continue
            mqtt_targets.append(sn)

        mqtt_stats = publish_mqtt_many(
            mqtt_targets, message=MQTT_STRATEGY_PULL_PAYLOAD, qos=1
        )
        stats = {
            "apply_status": "done",
            "snapshot_ok": len(notify_sns),
            "snapshot_failed": snapshot_failed,
            "notified": int(mqtt_stats.get("notified") or 0),
            "notify_failed": int(mqtt_stats.get("failed") or 0),
            "skipped_offline": skipped_offline,
        }
        _merge_task_ext(db, tid, stats)
        db.commit()
        logger.info(
            "策略下发后台完成 task=%s 目标=%s 快照成功=%s 失败=%s 通知=%s 离线跳过=%s 通知失败=%s",
            tid,
            len(device_rows),
            stats["snapshot_ok"],
            snapshot_failed,
            stats["notified"],
            skipped_offline,
            stats["notify_failed"],
        )
    except Exception:
        logger.exception("策略下发后台任务异常 task_id=%s", tid)
        try:
            db.rollback()
            _merge_task_ext(db, tid, {"apply_status": "failed"})
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()


def flush_pending_policy_notifies(
    online_sns: list[str] | set[str] | None = None,
    db: Session | None = None,
) -> int:
    """设备上线后：对「快照不匹配」的在线设备补发 STRATEGY_PULL 通知."""
    sns = {str(x).strip() for x in (online_sns or []) if str(x).strip()}
    if not sns:
        return 0

    own_session = db is None
    if own_session:
        db = SessionLocal()
    sent = 0
    try:
        for sn in sns:
            cmp = device_snapshot_service.get_device_snapshot_compare(db, sn)
            if cmp.get("consistent"):
                continue
            try:
                publish_mqtt(sn=sn, message=MQTT_STRATEGY_PULL_PAYLOAD, qos=1)
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("上线补发策略通知失败 sn=%s: %s", sn, exc)
        if sent:
            logger.info("上线补发策略通知（快照不匹配）：%s 台", sent)
        return sent
    except Exception:  # noqa: BLE001
        logger.exception("上线补发策略通知失败")
        return 0
    finally:
        if own_session and db is not None:
            db.close()


def get_strategy_for_device(db: Session, sn: str) -> dict[str, Any]:
    """设备拉取策略：最新变更单的紧急度/截止时间 + 当前全部预期快照.

    最新任务按该 SN 在 t_policy_device_task 关联的 t_policy_task.create_time 倒序取一条。

    若设备已解绑（无成员或 bind_status≠1）：返回空 snapshot，并补发
    DEVICE_UNBINDING，覆盖解绑时离线未收到 MQTT 的情况。
    """
    sn = (sn or "").strip()
    if not sn:
        raise HTTPException(status_code=400, detail="请提供设备 SN")

    device = db.query(Device).filter(Device.sn == sn).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    unbound = device.member_id is None or int(device.bind_status or 0) != 1
    if unbound:
        try:
            publish_mqtt(sn=sn, message=MQTT_DEVICE_UNBINDING_PAYLOAD, qos=1)
            logger.info("解绑设备拉取策略，已补发 DEVICE_UNBINDING sn=%s", sn)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "解绑设备拉取策略时补发 DEVICE_UNBINDING 失败 sn=%s: %s", sn, exc
            )
        return {
            "policyLevel": None,
            "latestExecutionTime": None,
            "snapshot": [],
        }

    latest_task = (
        db.query(PolicyTask)
        .join(PolicyDeviceTask, PolicyDeviceTask.task_id == PolicyTask.id)
        .filter(PolicyDeviceTask.device_sn == sn)
        .order_by(PolicyTask.create_time.desc(), PolicyTask.id.desc())
        .first()
    )

    policy_level: str | None = None
    latest_execution_time: str | None = None
    if latest_task is not None:
        level = (latest_task.policy_level or "").strip()
        if level not in ("normal", "urgent"):
            # 兼容旧数据：有截止时间视为普通，否则紧急
            level = "normal" if latest_task.deadline_at else "urgent"
        policy_level = level
        if level == "normal" and latest_task.deadline_at:
            latest_execution_time = _fmt(latest_task.deadline_at)

    snapshot = device_snapshot_service.build_expected_snapshot_payload(db, sn)
    return {
        "policyLevel": policy_level,
        "latestExecutionTime": latest_execution_time,
        "snapshot": snapshot,
    }


def on_device_strategy_pulled(db: Session, sn: str) -> dict[str, Any]:
    """兼容旧调用名，等同 get_strategy_for_device."""
    return get_strategy_for_device(db, sn)
