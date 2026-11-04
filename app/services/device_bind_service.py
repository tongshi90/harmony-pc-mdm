"""设备侧 · 成员绑定（绑定成功后套用部门初始策略）."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.enums.policy_change_op import INITIAL_BIND, resolve_policy_timing
from app.models.department import SysDepartment, SysMember
from app.models.device import Device, DeviceAppInstalled
from app.models.device_snapshot import DevicePolicyCurrent, DevicePolicyExpected
from app.models.initial_policy import InitialPolicy, InitialPolicyItem
from app.models.policy_task import PolicyDeviceTask, PolicyTask, PolicyTaskItem
from app.mqtt import publish_mqtt
from app.services import device_snapshot_service
from app.services.policy_dispatch_service import (
    MQTT_DEVICE_UNBINDING_PAYLOAD,
    MQTT_STRATEGY_PULL_PAYLOAD,
)
from app.utils.policy_summary import (
    aggregate_policy_summaries,
    build_policy_item_summary,
    make_app_name_resolver,
)
from app.utils.security import verify_password
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

logger = logging.getLogger("mdm.device.bind")


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _parse_param(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_initial_policy(
    db: Session, dept: SysDepartment | None
) -> InitialPolicy | None:
    """仅使用分组绑定的初始策略模板；未设置则不套用（无全局默认）."""
    if dept is None or dept.initial_policy_id is None:
        return None
    return (
        db.query(InitialPolicy)
        .filter(InitialPolicy.id == int(dept.initial_policy_id))
        .first()
    )


def _load_policy_items(
    db: Session, policy_id: int
) -> list[tuple[str, dict, int, str]]:
    """返回 (policy_code, param, sort, summary)."""
    rows = (
        db.query(InitialPolicyItem)
        .filter(InitialPolicyItem.policy_id == policy_id)
        .order_by(InitialPolicyItem.sort_order.asc(), InitialPolicyItem.id.asc())
        .all()
    )
    resolve = make_app_name_resolver(db)
    out: list[tuple[str, dict, int, str]] = []
    for i, r in enumerate(rows):
        code = (r.policy_code or "").strip()
        if code == "PASSWORD_POLICY":
            code = "PSW_MANAGEMENT"
        if not code:
            continue
        param = _parse_param(r.param_json)
        sort = int(r.sort_order or i + 1)
        summary = (r.summary or "").strip() or build_policy_item_summary(
            code, param, resolve_app_name=resolve
        )
        out.append((code, param, sort, summary))
    return out


def _apply_initial_policy(
    db: Session,
    *,
    device: Device,
    member: SysMember,
    dept: SysDepartment | None,
    ts,
) -> None:
    """写入初始策略变更日志 + 预期快照（同一会话，由调用方统一 commit）."""
    template = _resolve_initial_policy(db, dept)
    if not template:
        logger.warning(
            "设备绑定无可用初始策略模板 sn=%s member=%s dept=%s",
            device.sn,
            member.id,
            dept.id if dept else None,
        )
        return

    items = _load_policy_items(db, int(template.id))
    level, wait_hours, deadline_at = resolve_policy_timing(
        op_type=INITIAL_BIND, now=ts
    )
    task_id = snowflake_id()
    sn = (device.sn or "").strip()
    dept_name = (dept.name if dept else "") or ""
    summaries = [s for _c, _p, _o, s in items]
    ext = {
        "template_id": str(template.id),
        "template_name": template.name,
        "department_id": str(dept.id) if dept else None,
        "department_name": dept_name,
        "member_id": str(member.id),
        "member_account": member.account,
    }

    db.add(
        PolicyTask(
            id=task_id,
            op_type=INITIAL_BIND,
            name=f"初始策略 · {template.name} · {sn}",
            policy_level=level,
            wait_hours=wait_hours,
            deadline_at=deadline_at,
            target_json=_dumps([str(dept.id)] if dept else []),
            target_desc=f"设备绑定 · {sn} · {member.name or member.account}",
            source_id=int(template.id),
            ext_json=_dumps(ext),
            creator_id=None,
            creator_name="设备绑定",
            target_count=1,
            policy_summary=aggregate_policy_summaries(summaries) if summaries else "空初始策略",
            create_time=ts,
            update_time=ts,
        )
    )

    for code, param, sort, summary in items:
        db.add(
            PolicyTaskItem(
                id=snowflake_id(),
                task_id=task_id,
                policy_code=code,
                param_json=_dumps(param),
                summary=summary,
                sort_order=sort,
                create_time=ts,
                update_time=ts,
            )
        )
        device_snapshot_service.upsert_expected(
            db,
            device_sn=sn,
            policy_code=code,
            param=param,
            commit=False,
        )

    db.add(
        PolicyDeviceTask(
            id=snowflake_id(),
            task_id=task_id,
            device_id=device.id,
            device_sn=sn,
            member_id=member.id,
            member_name=member.name,
            employee_id=member.employee_id,
            department_id=member.department_id,
            department_path=(
                (dept.path if dept else None) or (dept.name if dept else None)
            ),
            create_time=ts,
            update_time=ts,
        )
    )
    # 预期快照写入后重算合规（通常尚无当前上报 → 多为不合规，待设备上报后纠正）
    device_snapshot_service.refresh_device_compliance(db, sn, commit=False)
    logger.info(
        "绑定套用初始策略 sn=%s template=%s items=%s task=%s",
        sn,
        template.id,
        len(items),
        task_id,
    )


def _bind_success_payload(db: Session, member: SysMember) -> dict:
    dept = (
        db.query(SysDepartment)
        .filter(SysDepartment.id == member.department_id)
        .first()
    )
    return {
        "name": member.name or "",
        "groupName": (dept.name if dept else "") or "",
    }


def bind_device(
    db: Session,
    *,
    sn: str,
    user_name: str,
    password: str,
) -> dict:
    """将设备与成员绑定，并落库初始策略后才返回成功.

    条件：
    - SN 存在；账号密码匹配启用中的成员
    - 若该设备与该成员已是相互绑定：幂等成功（重复点击不失败），不重复套用初始策略
    - 否则：设备须未绑定，且该成员未绑定其它设备

    新绑定成功路径：绑定关系 + 初始策略三表日志 + 预期快照 同一事务提交，
    保证随后 /api/strategy/get 能拉到初始策略。
    """
    device_sn = (sn or "").strip()
    account = (user_name or "").strip()
    plain = password or ""
    if not device_sn:
        raise HTTPException(status_code=400, detail="请提供设备 SN")
    if not account:
        raise HTTPException(status_code=400, detail="请提供账号")
    if not plain:
        raise HTTPException(status_code=400, detail="请提供密码")

    device = db.query(Device).filter(Device.sn == device_sn).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    member = (
        db.query(SysMember)
        .filter(
            SysMember.account == account,
            SysMember.is_delete == 0,
        )
        .first()
    )
    if not member or not verify_password(plain, member.password or ""):
        raise HTTPException(status_code=400, detail="账号或密码错误")
    if int(member.status or 0) != 1:
        raise HTTPException(status_code=400, detail="账号已禁用")

    # 已是「此人 ↔ 此设备」相互绑定：幂等成功（须双方互指，不可仅一方匹配）
    device_bound = device.member_id is not None or int(device.bind_status or 0) == 1
    already_paired = (
        device.member_id is not None
        and int(device.member_id) == int(member.id)
        and int(device.bind_status or 0) == 1
    )
    if already_paired:
        # 成员名下不应再挂其它设备；若有脏数据仍拒绝
        other = (
            db.query(Device.id)
            .filter(Device.member_id == member.id, Device.id != device.id)
            .first()
        )
        if other:
            raise HTTPException(status_code=400, detail="该成员已绑定其它设备")
        return _bind_success_payload(db, member)

    if device_bound:
        raise HTTPException(status_code=400, detail="设备已被绑定")

    bound_other = (
        db.query(Device.id)
        .filter(Device.member_id == member.id)
        .first()
    )
    if bound_other:
        raise HTTPException(status_code=400, detail="该成员已绑定其它设备")

    dept = (
        db.query(SysDepartment)
        .filter(SysDepartment.id == member.department_id)
        .first()
    )

    ts = local_now()
    device.member_id = member.id
    device.bind_status = 1
    if not device.activate_time:
        device.activate_time = ts
    device.update_time = ts

    # 先写完该设备全部预期快照并 commit，再发 MQTT（与策略下发 / 应用批量同一约束）
    try:
        _apply_initial_policy(
            db, device=device, member=member, dept=dept, ts=ts
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("设备绑定落库失败 sn=%s", device_sn)
        raise HTTPException(status_code=500, detail="绑定失败，请稍后重试") from None

    # 仅在快照已提交后通知；MQTT 失败不影响已成功的绑定与策略落库
    try:
        publish_mqtt(sn=device_sn, message=MQTT_STRATEGY_PULL_PAYLOAD, qos=1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("绑定后策略通知失败 sn=%s: %s", device_sn, exc)

    return _bind_success_payload(db, member)


def unbind_device(db: Session, *, sn: str, notify_mqtt: bool = True) -> dict:
    """管理台解绑：清绑定、快照、已装应用、设备任务明细，并可选 MQTT 通知.

    对外入口仅 POST /platform/device/{sn}/unbind；设备侧不再开放解绑。
    清理顺序在同一事务内完成后再 commit，随后按需发送 DEVICE_UNBINDING。
    notify_mqtt=False 时仅落库（如数据擦除改发 DISK_ERASURE）。
    """
    device_sn = (sn or "").strip()
    if not device_sn:
        raise HTTPException(status_code=400, detail="请提供设备 SN")

    device = db.query(Device).filter(Device.sn == device_sn).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.member_id is None and int(device.bind_status or 0) == 0:
        raise HTTPException(status_code=400, detail="设备当前未绑定")

    ts = local_now()
    try:
        # 1) 解除人员绑定
        device.member_id = None
        device.bind_status = 0
        device.activate_time = None
        device.update_time = ts

        # 2) 预期 / 当前策略快照
        db.query(DevicePolicyExpected).filter(
            DevicePolicyExpected.device_sn == device_sn
        ).delete(synchronize_session=False)
        db.query(DevicePolicyCurrent).filter(
            DevicePolicyCurrent.device_sn == device_sn
        ).delete(synchronize_session=False)

        # 3) 已安装应用
        db.query(DeviceAppInstalled).filter(
            DeviceAppInstalled.device_id == device.id
        ).delete(synchronize_session=False)

        # 4) 策略变更 · 设备明细日志
        db.query(PolicyDeviceTask).filter(
            (PolicyDeviceTask.device_sn == device_sn)
            | (PolicyDeviceTask.device_id == device.id)
        ).delete(synchronize_session=False)

        # 5) 快照已清空 → 视为合规、无差异
        device.is_compliant = 1
        device.policy_diff_count = 0

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("设备解绑落库失败 sn=%s", device_sn)
        raise HTTPException(status_code=500, detail="解绑失败，请稍后重试") from None

    mqtt_ok = False
    mqtt_error = ""
    if notify_mqtt:
        try:
            publish_mqtt(sn=device_sn, message=MQTT_DEVICE_UNBINDING_PAYLOAD, qos=1)
            mqtt_ok = True
        except Exception as exc:  # noqa: BLE001
            mqtt_error = str(exc)
            logger.warning("解绑 MQTT 通知失败 sn=%s: %s", device_sn, exc)

    logger.info(
        "设备已解绑 sn=%s mqtt_ok=%s notify=%s",
        device_sn,
        mqtt_ok,
        notify_mqtt,
    )
    return {
        "sn": device_sn,
        "mqtt_notified": mqtt_ok,
        "mqtt_error": mqtt_error or None,
    }
