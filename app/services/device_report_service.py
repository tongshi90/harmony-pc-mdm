"""设备侧上报：位置、当前快照等."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.app_pkg import AppBase, AppVersion
from app.models.device import Device, DeviceAppInstalled
from app.models.device_location import DeviceLocationLog
from app.services import device_snapshot_service
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

# 应用安装管理不写入当前策略表，由 appInfos → t_device_app_installed 分析
_SNAPSHOT_SKIP_CODES = frozenset({"APP_MANAGEMENT"})


def _parse_coord(value: str, *, label: str) -> str:
    text = (value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"请提供{label}")
    try:
        float(text)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{label}格式无效") from exc
    return text


def report_location(
    db: Session,
    *,
    sn: str,
    longitude: str,
    latitude: str,
) -> dict:
    """保存设备位置上报日志."""
    device_sn = (sn or "").strip()
    if not device_sn:
        raise HTTPException(status_code=400, detail="请提供设备 SN")

    lon = _parse_coord(longitude, label="经度")
    lat = _parse_coord(latitude, label="纬度")

    device = db.query(Device).filter(Device.sn == device_sn).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    ts = local_now()
    row = DeviceLocationLog(
        id=snowflake_id(),
        device_id=device.id,
        device_sn=device_sn,
        longitude=lon,
        latitude=lat,
        report_time=ts,
        create_time=ts,
    )
    db.add(row)
    db.commit()
    return {}


def _match_app_version(versions: list[AppVersion], version: str) -> AppVersion | None:
    """按版本名优先，其次版本号匹配."""
    text = (version or "").strip()
    if not text:
        return None
    for v in versions:
        if (v.version_name or "").strip() == text:
            return v
    for v in versions:
        if (v.version_code or "").strip() == text:
            return v
    return None


def _replace_installed_apps(
    db: Session,
    *,
    device: Device,
    app_infos: list[Any],
) -> dict[str, int]:
    """按上报 appInfos 全量覆盖已安装应用（未知 appId / 无匹配版本则跳过）."""
    ts = local_now()
    db.query(DeviceAppInstalled).filter(
        DeviceAppInstalled.device_id == device.id
    ).delete()

    accepted = 0
    skipped = 0
    seen_app_pks: set[int] = set()

    for item in app_infos or []:
        app_id = (getattr(item, "appId", None) or "").strip()
        version = (getattr(item, "version", None) or "").strip()
        if not app_id or not version:
            skipped += 1
            continue
        app = (
            db.query(AppBase)
            .filter(AppBase.app_id == app_id)
            .first()
        )
        if not app:
            skipped += 1
            continue
        if int(app.id) in seen_app_pks:
            skipped += 1
            continue
        versions = (
            db.query(AppVersion)
            .filter(AppVersion.app_id == app.id)
            .order_by(AppVersion.id.desc())
            .all()
        )
        ver = _match_app_version(versions, version)
        if not ver:
            skipped += 1
            continue
        db.add(
            DeviceAppInstalled(
                id=snowflake_id(),
                device_id=device.id,
                app_id=app.id,
                app_version_id=ver.id,
                install_type=2,
                install_time=ts,
                create_time=ts,
            )
        )
        seen_app_pks.add(int(app.id))
        accepted += 1

    return {"accepted": accepted, "skipped": skipped}


# deviceInfo 字段 → t_device 列（仅 basic_info_synced=0 时写入）
_DEVICE_INFO_FIELD_MAP = {
    "deviceName": "device_name",
    "device_name": "device_name",
    "model": "model",
    "modelVersion": "model_version",
    "model_version": "model_version",
    "vendor": "vendor",
    "serialNumber": "serial_number",
    "serial_number": "serial_number",
    "imei": "imei",
    "os": "os",
    "osBuild": "os_build",
    "os_build": "os_build",
    "cpu": "cpu",
    "memory": "memory",
    "disk": "disk",
    "gpu": "gpu",
    "biosVersion": "bios_version",
    "bios_version": "bios_version",
    "hostname": "hostname",
    "ip": "ip",
    "mac": "mac",
    "subnet": "subnet",
    "gateway": "gateway",
    "dns": "dns",
    "agentVersion": "agent_version",
    "agent_version": "agent_version",
    "mqttClientId": "mqtt_client_id",
    "mqtt_client_id": "mqtt_client_id",
}


def _apply_device_info_once(device: Device, device_info: dict[str, Any] | None) -> bool:
    """首次写入基本信息：basic_info_synced=1 则整包忽略；否则填空列并置位.

    返回本次是否完成首次同步（含已置位）。
    """
    if int(getattr(device, "basic_info_synced", 0) or 0) == 1:
        return False
    if not device_info or not isinstance(device_info, dict):
        return False

    has_payload = False
    for src_key, col in _DEVICE_INFO_FIELD_MAP.items():
        if src_key not in device_info:
            continue
        raw = device_info.get(src_key)
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        has_payload = True
        cur = getattr(device, col, None)
        if cur is not None and str(cur).strip():
            continue
        setattr(device, col, text[:255] if col != "remark" else text)

    if not has_payload:
        return False

    device.basic_info_synced = 1
    device.update_time = local_now()
    return True


def report_snapshot(
    db: Session,
    *,
    sn: str,
    snapshot: list[dict[str, Any]] | None,
    app_infos: list[Any] | None,
    device_info: dict[str, Any] | None = None,
) -> dict:
    """设备上报当前策略快照 + 已装应用（全量覆盖）；deviceInfo 仅未同步时写入并置位."""
    device_sn = (sn or "").strip()
    if not device_sn:
        raise HTTPException(status_code=400, detail="请提供设备 SN")

    device = db.query(Device).filter(Device.sn == device_sn).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    items = snapshot if isinstance(snapshot, list) else []
    apps = app_infos if isinstance(app_infos, list) else []

    basic_written = _apply_device_info_once(device, device_info)

    # 策略当前快照：全量替换；未上报的类型删除；APP_MANAGEMENT 跳过
    saved = device_snapshot_service.replace_current_snapshot(
        db,
        device_sn=device_sn,
        items=items,
        skip_codes=_SNAPSHOT_SKIP_CODES,
        commit=False,
    )
    app_stats = _replace_installed_apps(db, device=device, app_infos=apps)
    # 先 flush，确保合规比对能读到刚写入的当前快照与已装应用
    db.flush()
    compliant = device_snapshot_service.refresh_device_compliance(
        db, device_sn, commit=False
    )
    db.commit()

    return {
        "snapshot_count": len(saved),
        "app_accepted": app_stats["accepted"],
        "app_skipped": app_stats["skipped"],
        "basic_info_written": basic_written,
        "compliant": compliant,
    }
