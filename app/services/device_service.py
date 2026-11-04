"""设备管理：列表 / 详情 / 已安装应用；快照复用 device_snapshot_service."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.app_pkg import AppBase, AppVersion
from app.models.department import SysDepartment, SysMember
from app.models.device import Device, DeviceAppInstalled
from app.models.device_location import DeviceLocationLog
from app.models.device_snapshot import DevicePolicyCurrent, DevicePolicyExpected
from app.models.policy_task import PolicyDeviceTask
from app.mqtt import publish_mqtt
from app.services import device_snapshot_service
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

_MQTT_STRATEGY_PULL_PAYLOAD = '{"type":"STRATEGY_PULL"}'
_MQTT_SNAPSHOT_REPORT_PAYLOAD = '{"type":"SNAPSHOT_REPORT"}'

def _fmt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _status_label(status: int) -> str:
    return {1: "online", 2: "offline", 3: "lost"}.get(int(status or 2), "offline")


def _get_device_by_sn(db: Session, sn: str) -> Device:
    row = db.query(Device).filter(Device.sn == (sn or "").strip()).first()
    if not row:
        raise HTTPException(status_code=404, detail="设备不存在")
    return row


def _member_dept(
    db: Session, member_id: int | None
) -> tuple[SysMember | None, SysDepartment | None]:
    if not member_id:
        return None, None
    member = (
        db.query(SysMember)
        .filter(SysMember.id == member_id, SysMember.is_delete == 0)
        .first()
    )
    if not member:
        return None, None
    dept = (
        db.query(SysDepartment)
        .filter(SysDepartment.id == member.department_id)
        .first()
    )
    return member, dept


def _compliance_label(row: Device) -> str:
    return "compliant" if int(getattr(row, "is_compliant", 1) or 0) == 1 else "non-compliant"


def _list_item(db: Session, row: Device, *, with_compliance: bool = True) -> dict[str, Any]:
    member, dept = _member_dept(db, row.member_id)
    bound = bool(member) and int(row.bind_status or 0) == 1
    data = {
        "id": str(row.id),
        "sn": row.sn,
        "device_name": row.device_name or "",
        "model": row.model or "",
        "model_version": row.model_version or "",
        "vendor": row.vendor or "",
        "serial_number": row.serial_number or "",
        "status": _status_label(row.status),
        "status_code": row.status,
        "bind_status": row.bind_status,
        "bound": bound,
        "member_id": str(member.id) if member else None,
        "member_name": member.name if member else None,
        "employee_id": member.employee_id if member else None,
        "department_path": (dept.path if dept else "") or "",
        "department_name": dept.name if dept else "",
        "online_time": _fmt(row.online_time),
        "activate_time": _fmt(row.activate_time),
        "update_time": _fmt(row.update_time),
    }
    if with_compliance:
        data["compliance"] = _compliance_label(row)
        data["is_compliant"] = int(getattr(row, "is_compliant", 1) or 0)
        data["diff_count"] = int(getattr(row, "policy_diff_count", 0) or 0)
    synced = has_basic_info(row)
    data["has_basic_info"] = synced
    data["basic_info_synced"] = 1 if synced else 0
    return data


def _detail_out(db: Session, row: Device) -> dict[str, Any]:
    base = _list_item(db, row, with_compliance=True)
    base.update(
        {
            "imei": row.imei or "",
            "os": row.os or "",
            "os_build": row.os_build or "",
            "cpu": row.cpu or "",
            "memory": row.memory or "",
            "disk": row.disk or "",
            "gpu": row.gpu or "",
            "bios_version": row.bios_version or "",
            "hostname": row.hostname or "",
            "ip": row.ip or "",
            "mac": row.mac or "",
            "subnet": row.subnet or "",
            "gateway": row.gateway or "",
            "dns": row.dns or "",
            "agent_version": row.agent_version or "",
            "mqtt_client_id": row.mqtt_client_id or "",
            "remark": row.remark or "",
            "create_time": _fmt(row.create_time),
        }
    )
    return base


def list_devices(
    db: Session,
    *,
    keyword: str | None = None,
    status: str | None = None,
    bind: str | None = None,
    compliance: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    q = db.query(Device)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        member_ids = [
            m.id
            for m in db.query(SysMember)
            .filter(SysMember.is_delete == 0, SysMember.name.like(like))
            .all()
        ]
        if member_ids:
            q = q.filter(
                (Device.sn.like(like))
                | (Device.model.like(like))
                | (Device.member_id.in_(member_ids))
            )
        else:
            q = q.filter((Device.sn.like(like)) | (Device.model.like(like)))

    st = (status or "").strip().lower()
    if st == "online":
        q = q.filter(Device.status == 1)
    elif st == "offline":
        q = q.filter(Device.status == 2)
    elif st == "lost":
        q = q.filter(Device.status == 3)

    bd = (bind or "").strip().lower()
    if bd == "bound":
        q = q.filter(Device.bind_status == 1, Device.member_id.isnot(None))
    elif bd == "unbound":
        q = q.filter((Device.bind_status == 0) | (Device.member_id.is_(None)))

    cp = (compliance or "").strip().lower().replace("_", "-")
    if cp in ("noncompliant", "non-compliant"):
        q = q.filter(Device.is_compliant == 0)
    elif cp in ("compliant",):
        q = q.filter(Device.is_compliant == 1)

    total = q.count()
    rows = (
        q.order_by(Device.create_time.asc(), Device.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_list_item(db, r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_device(db: Session, sn: str) -> dict:
    return _detail_out(db, _get_device_by_sn(db, sn))


def _normalize_sn(sn: str) -> str:
    return (sn or "").strip()


def create_device(db: Session, sn: str) -> dict:
    """预登记设备：仅写入 SN；已存在则失败."""
    device_sn = _normalize_sn(sn)
    if not device_sn:
        raise HTTPException(status_code=400, detail="请提供设备 SN")
    if len(device_sn) > 64:
        raise HTTPException(status_code=400, detail="设备 SN 长度不能超过 64")
    exists = db.query(Device.id).filter(Device.sn == device_sn).first()
    if exists:
        raise HTTPException(status_code=400, detail="设备 SN 已存在")
    now = local_now()
    row = Device(
        id=snowflake_id(),
        sn=device_sn,
        member_id=None,
        bind_status=0,
        status=2,  # 离线
        is_compliant=1,
        policy_diff_count=0,
        basic_info_synced=0,
        create_time=now,
        update_time=now,
    )
    db.add(row)
    db.commit()
    return _list_item(db, row, with_compliance=True)


def batch_create_devices(db: Session, sns: list[str]) -> dict:
    """批量预登记：逐条尝试，部分失败不回滚整批."""
    created: list[dict] = []
    failed: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in sns or []:
        sn = _normalize_sn(raw)
        if not sn:
            continue
        if sn in seen:
            failed.append({"sn": sn, "reason": "本批内重复"})
            continue
        seen.add(sn)
        if len(sn) > 64:
            failed.append({"sn": sn, "reason": "SN 长度不能超过 64"})
            continue
        try:
            item = create_device(db, sn)
            created.append(item)
        except HTTPException as exc:
            detail = exc.detail
            reason = detail if isinstance(detail, str) else "登记失败"
            failed.append({"sn": sn, "reason": reason})
    return {
        "created": created,
        "failed": failed,
        "created_count": len(created),
        "failed_count": len(failed),
    }


def has_basic_info(device: Device) -> bool:
    """是否已完成基本信息首次同步（t_device.basic_info_synced=1）."""
    return int(getattr(device, "basic_info_synced", 0) or 0) == 1


def delete_device(db: Session, sn: str) -> None:
    """删除未绑定设备及其附属数据；已绑定设备禁止删除."""
    device = _get_device_by_sn(db, sn)
    member, _ = _member_dept(db, device.member_id)
    bound = bool(member) and int(device.bind_status or 0) == 1
    if bound:
        raise HTTPException(status_code=400, detail="仅可删除未绑定的设备，请先解绑")
    if device.member_id is not None or int(device.bind_status or 0) != 0:
        raise HTTPException(status_code=400, detail="仅可删除未绑定的设备")

    device_sn = device.sn
    device_id = device.id
    try:
        db.query(DevicePolicyExpected).filter(
            DevicePolicyExpected.device_sn == device_sn
        ).delete(synchronize_session=False)
        db.query(DevicePolicyCurrent).filter(
            DevicePolicyCurrent.device_sn == device_sn
        ).delete(synchronize_session=False)
        db.query(DeviceAppInstalled).filter(
            DeviceAppInstalled.device_id == device_id
        ).delete(synchronize_session=False)
        db.query(DeviceLocationLog).filter(
            (DeviceLocationLog.device_sn == device_sn)
            | (DeviceLocationLog.device_id == device_id)
        ).delete(synchronize_session=False)
        db.query(PolicyDeviceTask).filter(
            (PolicyDeviceTask.device_sn == device_sn)
            | (PolicyDeviceTask.device_id == device_id)
        ).delete(synchronize_session=False)
        db.delete(device)
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="删除失败，请稍后重试") from None


def get_device_snapshot(db: Session, sn: str) -> dict:
    _get_device_by_sn(db, sn)
    return device_snapshot_service.get_device_snapshot_compare(db, sn)


def list_installed_apps(db: Session, sn: str) -> dict:
    device = _get_device_by_sn(db, sn)
    rows = (
        db.query(DeviceAppInstalled, AppBase, AppVersion)
        .join(AppBase, AppBase.id == DeviceAppInstalled.app_id)
        .join(AppVersion, AppVersion.id == DeviceAppInstalled.app_version_id)
        .filter(DeviceAppInstalled.device_id == device.id)
        .order_by(DeviceAppInstalled.install_time.desc(), DeviceAppInstalled.id.desc())
        .all()
    )
    items = []
    for inst, app, ver in rows:
        items.append(
            {
                "id": str(inst.id),
                "app_id": str(app.id),
                "app_name": app.app_name,
                "bundle_name": app.bundle_name or app.app_code or "",
                "app_code": app.app_code,
                "version_id": str(ver.id),
                "version_name": ver.version_name,
                "version_code": ver.version_code,
                "install_type": inst.install_type,
                "install_type_label": {1: "MDM 下发", 2: "用户安装"}.get(
                    int(inst.install_type or 0), "—"
                ),
                "install_time": _fmt(inst.install_time),
            }
        )
    return {"items": items, "total": len(items)}


def list_location_logs(
    db: Session,
    sn: str,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """设备轨迹：按上报时间倒序分页查询 t_device_location_log."""
    device = _get_device_by_sn(db, sn)
    q = db.query(DeviceLocationLog).filter(DeviceLocationLog.device_sn == device.sn)
    total = q.count()
    rows = (
        q.order_by(
            DeviceLocationLog.report_time.desc(),
            DeviceLocationLog.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        {
            "id": str(r.id),
            "device_sn": r.device_sn,
            "longitude": r.longitude,
            "latitude": r.latitude,
            "report_time": _fmt(r.report_time),
            "create_time": _fmt(r.create_time),
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def notify_strategy_pull(db: Session, sn: str) -> dict[str, Any]:
    """不合规设备补发 STRATEGY_PULL，通知端侧重新拉取预期策略."""
    device = _get_device_by_sn(db, sn)
    member, _ = _member_dept(db, device.member_id)
    bound = bool(member) and int(device.bind_status or 0) == 1
    if not bound:
        raise HTTPException(status_code=400, detail="设备未绑定，无法补发策略")
    if int(getattr(device, "is_compliant", 1) or 0) == 1:
        raise HTTPException(status_code=400, detail="设备已合规，无需补发")

    # 下发前尽量校准在线状态
    try:
        from app.services.device_online_sync_service import sync_device_online_status

        sync_device_online_status(db)
        db.refresh(device)
    except Exception:  # noqa: BLE001
        pass

    device_sn = device.sn
    if int(device.status or 2) != 1:
        return {
            "sn": device_sn,
            "delivered": False,
            "skipped": True,
            "message": "设备离线，策略通知未下发",
        }

    try:
        publish_mqtt(sn=device_sn, message=_MQTT_STRATEGY_PULL_PAYLOAD, qos=1)
    except Exception as exc:  # noqa: BLE001
        return {
            "sn": device_sn,
            "delivered": False,
            "skipped": True,
            "message": f"MQTT 下发失败：{exc}",
        }
    return {
        "sn": device_sn,
        "delivered": True,
        "skipped": False,
        "message": "已通知设备重新拉取策略",
    }


def notify_snapshot_report(db: Session, sn: str) -> dict[str, Any]:
    """催设备完整上报：MQTT SNAPSHOT_REPORT（基本信息 + 已装应用 + 策略快照）."""
    device = _get_device_by_sn(db, sn)
    member, _ = _member_dept(db, device.member_id)
    bound = bool(member) and int(device.bind_status or 0) == 1
    if not bound:
        raise HTTPException(status_code=400, detail="设备未绑定，无法催设备上报")

    try:
        from app.services.device_online_sync_service import sync_device_online_status

        sync_device_online_status(db)
        db.refresh(device)
    except Exception:  # noqa: BLE001
        pass

    device_sn = device.sn
    if int(device.status or 2) != 1:
        return {
            "sn": device_sn,
            "delivered": False,
            "skipped": True,
            "message": "设备离线，上报通知未下发",
        }

    try:
        publish_mqtt(sn=device_sn, message=_MQTT_SNAPSHOT_REPORT_PAYLOAD, qos=1)
    except Exception as exc:  # noqa: BLE001
        return {
            "sn": device_sn,
            "delivered": False,
            "skipped": True,
            "message": f"MQTT 下发失败：{exc}",
        }
    return {
        "sn": device_sn,
        "delivered": True,
        "skipped": False,
        "message": "已通知设备上报（基本信息 / 已装应用 / 策略快照）",
    }
