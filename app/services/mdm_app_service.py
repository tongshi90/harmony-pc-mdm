from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import DATA_DIR, settings
from app.models.department import SysDepartment
from app.models.device import Device
from app.models.mdm_app import MdmAppVersion
from app.mqtt import publish_mqtt_many
from app.services.device_online_sync_service import sync_device_online_status
from app.services.device_snapshot_service import _version_key
from app.services.policy_dispatch_service import _resolve_targets
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

logger = logging.getLogger("mdm.mdm_app")

UPLOAD_ROOT = DATA_DIR / "uploads" / "mdm"
MQTT_MDM_UPDATE_PAYLOAD = '{"type":"MDM_UPDATE"}'


def _empty_expected() -> dict:
    return {
        "hasExpected": False,
        "bundleName": None,
        "versionId": None,
        "version": None,
        "versionCode": None,
        "bundleDownloadUrl": None,
        "bundleSize": None,
        "fileMd5": None,
    }


def _fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _ensure_hap(filename: str) -> None:
    name = (filename or "").strip().lower()
    if not name.endswith(".hap"):
        raise HTTPException(status_code=400, detail="仅支持上传 .hap 安装包")


def _version_out(v: MdmAppVersion) -> dict:
    return {
        "id": str(v.id),
        "version_name": v.version_name,
        "version_code": v.version_code,
        "file_name": v.file_name,
        "file_size": v.file_size,
        "file_md5": v.file_md5,
        "has_package": bool(v.file_path),
        "status": int(v.status or 0),
        "publish_time": _fmt(v.publish_time),
        "create_time": _fmt(v.create_time),
        "update_time": _fmt(v.update_time),
    }


def _pick_latest_published(versions: list[MdmAppVersion]) -> MdmAppVersion | None:
    published = [v for v in versions if int(v.status or 0) == 2 and v.file_path]
    if not published:
        published = [v for v in versions if int(v.status or 0) == 2]
    if not published:
        return None

    def sort_key(v: MdmAppVersion) -> tuple:
        return (_version_key(v.version_code), _version_key(v.version_name), int(v.id or 0))

    return max(published, key=sort_key)


def list_versions(db: Session) -> list[dict]:
    rows = (
        db.query(MdmAppVersion)
        .order_by(MdmAppVersion.id.desc())
        .all()
    )
    return [_version_out(v) for v in rows]


def get_version(db: Session, version_id: int) -> dict:
    v = db.query(MdmAppVersion).filter(MdmAppVersion.id == version_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="MDM 版本不存在")
    return _version_out(v)


def create_version(db: Session, data) -> dict:
    now = local_now()
    vid = snowflake_id()
    status = int(data.status)
    if status == 2:
        raise HTTPException(
            status_code=400,
            detail="请先创建草稿并上传安装包后再发布",
        )
    db.add(
        MdmAppVersion(
            id=vid,
            version_name=data.version_name.strip(),
            version_code=data.version_code.strip(),
            status=status,
            create_time=now,
            update_time=now,
        )
    )
    db.commit()
    return get_version(db, vid)


def update_version(db: Session, version_id: int, data) -> dict:
    v = db.query(MdmAppVersion).filter(MdmAppVersion.id == version_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="MDM 版本不存在")
    if data.version_name is not None:
        v.version_name = data.version_name.strip()
    if data.version_code is not None:
        v.version_code = data.version_code.strip()
    if data.status is not None:
        new_status = int(data.status)
        if new_status == 2 and not v.file_path:
            raise HTTPException(status_code=400, detail="请先上传 .hap 安装包后再发布")
        v.status = new_status
        if new_status == 2:
            v.publish_time = v.publish_time or local_now()
    v.update_time = local_now()
    db.commit()
    return get_version(db, version_id)


def delete_version(db: Session, version_id: int) -> None:
    v = db.query(MdmAppVersion).filter(MdmAppVersion.id == version_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="MDM 版本不存在")
    if int(v.status or 0) == 2:
        raise HTTPException(status_code=400, detail="请先取消发布后再删除")
    if v.file_path:
        path = DATA_DIR / v.file_path
        if path.is_file():
            path.unlink(missing_ok=True)
    db.delete(v)
    db.commit()


async def upload_package(db: Session, version_id: int, file: UploadFile) -> dict:
    v = db.query(MdmAppVersion).filter(MdmAppVersion.id == version_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="MDM 版本不存在")
    filename = file.filename or "package.hap"
    _ensure_hap(filename)

    dest_dir = UPLOAD_ROOT / str(version_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    dest = dest_dir / safe_name

    md5 = hashlib.md5()
    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            md5.update(chunk)
            out.write(chunk)

    if v.file_path:
        old = DATA_DIR / v.file_path
        if old.is_file() and old.resolve() != dest.resolve():
            old.unlink(missing_ok=True)

    rel = dest.relative_to(DATA_DIR).as_posix()
    v.file_name = safe_name
    v.file_path = rel
    v.file_size = size
    v.file_md5 = md5.hexdigest()
    v.update_time = local_now()
    db.commit()
    return get_version(db, version_id)


def get_package_path(db: Session, version_id: int) -> tuple[Path, str]:
    v = db.query(MdmAppVersion).filter(MdmAppVersion.id == version_id).first()
    if not v or not v.file_path:
        raise HTTPException(status_code=404, detail="安装包不存在")
    path = DATA_DIR / v.file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="安装包文件缺失")
    return path, v.file_name or path.name


def _absolute_download_url(base_url: str | None, version_id: int) -> str:
    path = f"/platform/mdm-app/versions/{version_id}/package"
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return path
    return f"{base}{path}"


def get_info_for_device(db: Session, *, public_base_url: str | None = None) -> dict:
    """端侧 GET /api/mdm/getInfo：全局最新已发布（不读设备预期）."""
    versions = db.query(MdmAppVersion).all()
    latest = _pick_latest_published(versions)
    if not latest or not latest.file_path:
        raise HTTPException(status_code=404, detail="暂无已发布的 MDM 安装包")

    size_bytes = int(latest.file_size or 0)
    bundle = (settings.agent_bundle_name or "").strip()
    return {
        "bundleName": bundle,
        "version": (latest.version_name or "").strip(),
        "bundleDownloadUrl": _absolute_download_url(public_base_url, int(latest.id)),
        "bundleSize": size_bytes // 1024,
    }


def _version_payload(
    v: MdmAppVersion, *, public_base_url: str | None, has_expected: bool
) -> dict:
    size_bytes = int(v.file_size or 0)
    return {
        "hasExpected": has_expected,
        "bundleName": (settings.agent_bundle_name or "").strip() or None,
        "versionId": str(v.id),
        "version": (v.version_name or "").strip() or None,
        "versionCode": (v.version_code or "").strip() or None,
        "bundleDownloadUrl": _absolute_download_url(public_base_url, int(v.id)),
        "bundleSize": size_bytes // 1024,
        "fileMd5": (v.file_md5 or "").strip() or None,
    }


def get_expected_for_device(
    db: Session, sn: str, *, public_base_url: str | None = None
) -> dict:
    """端侧 GET /api/mdm/expected：本机平台指定的预期版本（不回落最新）."""
    device_sn = (sn or "").strip()
    if not device_sn:
        raise HTTPException(status_code=400, detail="请提供设备 SN")

    device = db.query(Device).filter(Device.sn == device_sn).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    vid = device.expected_mdm_version_id
    if vid is None:
        return _empty_expected()

    v = db.query(MdmAppVersion).filter(MdmAppVersion.id == int(vid)).first()
    if not v or not v.file_path:
        raise HTTPException(
            status_code=400, detail="预期 MDM 版本安装包不可用，请联系管理员重新下发"
        )
    path = DATA_DIR / v.file_path
    if not path.is_file():
        raise HTTPException(
            status_code=400, detail="预期 MDM 版本安装包文件缺失，请联系管理员重新下发"
        )
    return _version_payload(v, public_base_url=public_base_url, has_expected=True)


def _load_published_version(db: Session, version_id: int) -> MdmAppVersion:
    v = db.query(MdmAppVersion).filter(MdmAppVersion.id == version_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="MDM 版本不存在")
    if int(v.status or 0) != 2:
        raise HTTPException(status_code=400, detail="仅可对已发布版本发起批量下发")
    if not v.file_path:
        raise HTTPException(status_code=400, detail="请先上传 .hap 安装包后再批量下发")
    path = DATA_DIR / v.file_path
    if not path.is_file():
        raise HTTPException(status_code=400, detail="安装包文件缺失，请重新上传")
    return v


def _resolve_group_targets(
    db: Session, *, group_ids: list[str], all_groups: bool
) -> tuple[list, str]:
    if all_groups:
        roots = (
            db.query(SysDepartment.id)
            .filter(SysDepartment.parent_id.is_(None))
            .order_by(SysDepartment.id.asc())
            .all()
        )
        ids = [str(r[0]) for r in roots]
        if not ids:
            rows = db.query(SysDepartment.id).order_by(SysDepartment.id.asc()).all()
            ids = [str(r[0]) for r in rows]
        if not ids:
            raise HTTPException(status_code=400, detail="暂无成员分组，请先创建分组")
        devices, group_desc, _ = _resolve_targets(
            db, target_type="group", group_ids=ids, member_ids=[]
        )
        people = group_desc.rsplit("·", 1)[-1].strip() if "·" in group_desc else ""
        desc = f"全部分组（含子组）· {people}" if people else "全部分组（含子组）"
        return devices, desc
    if not group_ids:
        raise HTTPException(status_code=400, detail="请选择成员分组")
    devices, desc, _ = _resolve_targets(
        db, target_type="group", group_ids=list(group_ids), member_ids=[]
    )
    return devices, desc


def batch_upgrade(
    db: Session,
    *,
    version_id: int,
    group_ids: list[str],
    all_groups: bool,
) -> dict:
    """按分组写入设备预期 MDM 版本，再对在线设备发 MDM_UPDATE."""
    ver = _load_published_version(db, version_id)
    devices, target_desc = _resolve_group_targets(
        db, group_ids=group_ids, all_groups=all_groups
    )
    if not devices:
        raise HTTPException(status_code=400, detail="所选范围内无可用设备")

    now = local_now()
    sns: list[str] = []
    seen: set[str] = set()
    for item in devices:
        device = item[0] if isinstance(item, tuple) else item
        sn = (getattr(device, "sn", None) or "").strip()
        if not sn or sn in seen:
            continue
        seen.add(sn)
        sns.append(sn)
        device.expected_mdm_version_id = int(ver.id)
        device.update_time = now

    db.commit()

    sync = sync_device_online_status()
    if sync.ok:
        online_set: set[str] | None = {
            str(x).strip() for x in sync.online_sns if str(x).strip()
        }
    else:
        online_set = None
        logger.warning(
            "MDM 批量下发在线同步失败，降级全量尝试通知: %s", sync.message
        )

    offline_skip = 0
    mqtt_targets: list[str] = []
    for sn in sns:
        if online_set is not None and sn not in online_set:
            offline_skip += 1
            continue
        mqtt_targets.append(sn)

    mqtt_stats = publish_mqtt_many(
        mqtt_targets, message=MQTT_MDM_UPDATE_PAYLOAD, qos=1
    )
    notified = int(mqtt_stats.get("notified") or 0)
    failed = int(mqtt_stats.get("failed") or 0)

    logger.info(
        "MDM 批量下发完成 version=%s targets=%s notified=%s offline=%s failed=%s",
        ver.id,
        len(sns),
        notified,
        offline_skip,
        failed,
    )
    return {
        "versionId": str(ver.id),
        "versionName": ver.version_name,
        "versionCode": ver.version_code,
        "targetDesc": target_desc,
        "targetCount": len(sns),
        "notified": notified,
        "offlineSkip": offline_skip,
        "failed": failed,
        "message": (
            f"已写入预期版本并通知在线设备"
            f"（目标 {len(sns)} 台，已通知 {notified}，离线跳过 {offline_skip}，失败 {failed}）"
        ),
    }
