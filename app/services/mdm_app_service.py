from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import DATA_DIR, settings
from app.models.mdm_app import MdmAppVersion
from app.services.device_snapshot_service import _version_key
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

UPLOAD_ROOT = DATA_DIR / "uploads" / "mdm"


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
    """端侧 GET /api/mdm/getInfo 返回 data 字段."""
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
