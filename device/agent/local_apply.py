"""将拉取到的策略落到模拟库（仅 device.db）."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.app_pkg import AppBase, AppVersion
from app.models.device import Device, DeviceAppInstalled
from app.models.device_snapshot import DevicePolicyCurrent
from app.services import device_snapshot_service
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

APP_CODE = "APP_MANAGEMENT"


def _policy_code_of(item: dict[str, Any]) -> str:
    return str(
        item.get("policy_code")
        or item.get("commandCode")
        or item.get("sceneCode")
        or ""
    ).strip()


def _ensure_device(db: Session, sn: str) -> Device:
    row = db.query(Device).filter(Device.sn == sn).first()
    if row:
        return row
    now = local_now()
    row = Device(
        id=snowflake_id(),
        sn=sn,
        bind_status=0,
        status=1,
        is_compliant=1,
        policy_diff_count=0,
        basic_info_synced=0,
        create_time=now,
        update_time=now,
    )
    db.add(row)
    db.flush()
    return row


def _match_app_version(versions: list[AppVersion], version: str) -> AppVersion | None:
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


def _replace_installed_from_app_mgmt(
    db: Session,
    *,
    device: Device,
    param: dict[str, Any],
) -> dict[str, int]:
    """按 APP_MANAGEMENT.currentApps 全量覆盖本机已装应用（跳过 uninstallApps 中的包）."""
    current_apps = param.get("currentApps") if isinstance(param, dict) else None
    uninstall = param.get("uninstallApps") if isinstance(param, dict) else None
    uninstall_set = {
        str(x).strip()
        for x in (uninstall if isinstance(uninstall, list) else [])
        if str(x).strip()
    }

    ts = local_now()
    db.query(DeviceAppInstalled).filter(
        DeviceAppInstalled.device_id == device.id
    ).delete()

    accepted = 0
    skipped = 0
    seen: set[int] = set()

    for entry in current_apps if isinstance(current_apps, list) else []:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        app_id = str(entry.get("appId") or "").strip()
        bundle = str(entry.get("bundleName") or "").strip()
        version = str(entry.get("version") or "").strip()
        if bundle and bundle in uninstall_set:
            skipped += 1
            continue
        if not app_id or not version:
            skipped += 1
            continue
        app = db.query(AppBase).filter(AppBase.app_id == app_id).first()
        if not app and bundle:
            app = db.query(AppBase).filter(AppBase.bundle_name == bundle).first()
        if not app:
            skipped += 1
            continue
        if int(app.id) in seen:
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
                install_type=1,
                install_time=ts,
                create_time=ts,
            )
        )
        seen.add(int(app.id))
        accepted += 1

    return {"accepted": accepted, "skipped": skipped}


def apply_pulled_snapshot(db: Session, sn: str, snapshot: list[dict[str, Any]]) -> dict[str, Any]:
    """拉取后本地「执行成功」：

    - 非 APP_MANAGEMENT：写入/覆盖 t_device_policy_expected 与 t_device_policy_current
    - APP_MANAGEMENT：写入 expected；不写 current 表；按 currentApps 更新已装应用表
    """
    device = _ensure_device(db, sn)
    items = snapshot if isinstance(snapshot, list) else []

    # 先同步 expected（含 APP_MANAGEMENT）
    for raw in items:
        if not isinstance(raw, dict):
            continue
        code = _policy_code_of(raw)
        if not code:
            continue
        param = raw.get("param") if isinstance(raw.get("param"), dict) else {}
        device_snapshot_service.upsert_expected(
            db, device_sn=sn, policy_code=code, param=param, commit=False
        )

    # 当前快照：跳过 APP_MANAGEMENT
    current_items = []
    app_param: dict[str, Any] | None = None
    for raw in items:
        if not isinstance(raw, dict):
            continue
        code = _policy_code_of(raw)
        if not code:
            continue
        if code == APP_CODE:
            app_param = raw.get("param") if isinstance(raw.get("param"), dict) else {}
            continue
        current_items.append(raw)

    saved = device_snapshot_service.replace_current_snapshot(
        db,
        device_sn=sn,
        items=current_items,
        skip_codes=frozenset({APP_CODE}),
        commit=False,
    )

    app_stats = {"accepted": 0, "skipped": 0}
    if app_param is not None:
        app_stats = _replace_installed_from_app_mgmt(
            db, device=device, param=app_param
        )
    else:
        # 拉取结果无 APP_MANAGEMENT：清空本地已装（与全量覆盖语义一致）
        db.query(DeviceAppInstalled).filter(
            DeviceAppInstalled.device_id == device.id
        ).delete()

    db.commit()
    return {
        "current_count": len(saved),
        "app_accepted": app_stats["accepted"],
        "app_skipped": app_stats["skipped"],
    }


def build_report_payload(db: Session, sn: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """从模拟库拼上报 snapshot + appInfos（对齐云侧协议）."""
    rows = (
        db.query(DevicePolicyCurrent)
        .filter(DevicePolicyCurrent.device_sn == sn)
        .all()
    )
    snapshot: list[dict[str, Any]] = []
    for r in rows:
        code = (r.policy_code or "").strip()
        if not code or code == APP_CODE:
            continue
        try:
            param = json.loads(r.param_json or "{}")
        except (TypeError, json.JSONDecodeError):
            param = {}
        if not isinstance(param, dict):
            param = {}
        key = device_snapshot_service.protocol_key_of(code)
        snapshot.append({key: code, "param": param})

    device = db.query(Device).filter(Device.sn == sn).first()
    app_infos: list[dict[str, str]] = []
    if device:
        installed = (
            db.query(DeviceAppInstalled, AppBase, AppVersion)
            .join(AppBase, AppBase.id == DeviceAppInstalled.app_id)
            .join(AppVersion, AppVersion.id == DeviceAppInstalled.app_version_id)
            .filter(DeviceAppInstalled.device_id == device.id)
            .all()
        )
        for _inst, app, ver in installed:
            app_infos.append(
                {
                    "appId": (app.app_id or "").strip(),
                    "version": (ver.version_name or ver.version_code or "").strip(),
                }
            )
    return snapshot, app_infos


def default_device_info(sn: str) -> dict[str, Any]:
    """模拟端首次上报用的基本信息（云侧仅首次落库）."""
    return {
        "deviceName": f"Sim-{sn}",
        "model": "MDM-Simulator",
        "modelVersion": "1.0",
        "vendor": "Simulator",
        "os": "HarmonyOS PC (Sim)",
        "osBuild": "sim-1",
        "cpu": "Sim CPU",
        "memory": "16GB",
        "disk": "512GB",
        "hostname": f"sim-{sn.lower()}",
        "ip": "127.0.0.1",
        "mac": "00:00:00:00:00:01",
        "agentVersion": "sim-0.1.0",
        "mqttClientId": sn,
    }
