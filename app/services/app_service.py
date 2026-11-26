from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models.app_pkg import AppBase, AppVersion
from app.models.department import SysDepartment, SysMember
from app.models.device import Device, DeviceAppInstalled
from app.models.device_snapshot import DevicePolicyExpected
from app.models.initial_policy import InitialPolicyItem
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

UPLOAD_ROOT = DATA_DIR / "uploads" / "apps"
ICON_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
ICON_MAX_BYTES = 2 * 1024 * 1024
POLICY_APP_MANAGEMENT = "APP_MANAGEMENT"


def _fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _ensure_hap(filename: str) -> None:
    name = (filename or "").strip().lower()
    if not (name.endswith(".hap") or name.endswith(".app") or name.endswith(".sap")):
        raise HTTPException(status_code=400, detail="仅支持上传 .hap / .app / .sap 安装包")


def _ensure_icon(filename: str) -> str:
    name = (filename or "").strip().lower()
    ext = Path(name).suffix
    if ext not in ICON_EXTS:
        raise HTTPException(
            status_code=400,
            detail="图标仅支持 png / jpg / jpeg / webp / gif / svg",
        )
    return ext


def _icon_url(app_id: int, has_icon: bool) -> str:
    return f"/platform/app/{app_id}/icon" if has_icon else ""


def _version_out(v: AppVersion) -> dict:
    has_pkg = bool(v.file_path)
    return {
        "id": str(v.id),
        "app_id": str(v.app_id),
        "version_name": v.version_name,
        "version_code": v.version_code,
        "file_name": v.file_name or "",
        "file_size": v.file_size,
        "file_md5": v.file_md5 or "",
        "has_package": has_pkg,
        "download_url": (
            f"/platform/app/{v.app_id}/versions/{v.id}/package" if has_pkg else ""
        ),
        "status": int(v.status or 0),
        "publish_time": _fmt(v.publish_time),
        "create_time": _fmt(v.create_time),
        "update_time": _fmt(v.update_time),
    }


def get_package_path(db: Session, app_id: int, version_id: int) -> tuple[Path, str]:
    """返回安装包本地路径与下载文件名."""
    v = (
        db.query(AppVersion)
        .filter(AppVersion.id == version_id, AppVersion.app_id == app_id)
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="应用版本不存在")
    if not v.file_path:
        raise HTTPException(status_code=404, detail="该版本尚未上传安装包")
    path = DATA_DIR / v.file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="安装包文件不存在")
    return path, v.file_name or path.name


def _app_out(db: Session, app: AppBase, *, detail: bool = False) -> dict:
    versions = (
        db.query(AppVersion)
        .filter(AppVersion.app_id == app.id)
        .order_by(AppVersion.id.desc())
        .all()
    )
    latest = next((v for v in versions if v.status == 2), None) or (
        versions[0] if versions else None
    )
    data = {
        "id": str(app.id),
        "app_name": app.app_name,
        "app_code": app.app_code,
        "app_id": app.app_id or "",
        "bundle_name": app.bundle_name or "",
        "app_icon": _icon_url(app.id, bool(app.app_icon)),
        "has_icon": bool(app.app_icon),
        "description": app.description or "",
        "status": int(app.status or 0),
        "version_count": len(versions),
        "latest_version": latest.version_name if latest else "",
        "create_time": _fmt(app.create_time),
        "update_time": _fmt(app.update_time),
    }
    if detail:
        data["versions"] = [_version_out(v) for v in versions]
    return data


def list_apps(
    db: Session, keyword: str | None = None, page: int = 1, page_size: int = 12
) -> dict:
    q = db.query(AppBase)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter((AppBase.app_name.like(like)) | (AppBase.app_code.like(like)))
    total = q.count()
    rows = (
        q.order_by(AppBase.update_time.desc(), AppBase.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_app_out(db, r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_app(db: Session, app_id: int) -> dict:
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    return _app_out(db, app, detail=True)


def _ensure_unique_app_identifiers(
    db: Session, *, app_id: str, bundle_name: str, exclude_pk: int | None = None
) -> None:
    q_aid = db.query(AppBase).filter(AppBase.app_id == app_id)
    q_bn = db.query(AppBase).filter(AppBase.bundle_name == bundle_name)
    if exclude_pk is not None:
        q_aid = q_aid.filter(AppBase.id != exclude_pk)
        q_bn = q_bn.filter(AppBase.id != exclude_pk)
    if q_aid.first():
        raise HTTPException(status_code=400, detail="App ID 已存在")
    if q_bn.first():
        raise HTTPException(status_code=400, detail="Bundle Name 已存在")


def _ensure_unique_version_fields(
    db: Session,
    *,
    app_id: int,
    version_name: str,
    version_code: str,
    exclude_id: int | None = None,
) -> None:
    """同一应用下版本名称、版本号均不可重复."""
    name = (version_name or "").strip()
    code = (version_code or "").strip()
    q_name = db.query(AppVersion).filter(
        AppVersion.app_id == app_id, AppVersion.version_name == name
    )
    q_code = db.query(AppVersion).filter(
        AppVersion.app_id == app_id, AppVersion.version_code == code
    )
    if exclude_id is not None:
        q_name = q_name.filter(AppVersion.id != exclude_id)
        q_code = q_code.filter(AppVersion.id != exclude_id)
    if q_name.first():
        raise HTTPException(status_code=400, detail="该应用下已存在相同的版本名称")
    if q_code.first():
        raise HTTPException(status_code=400, detail="该应用下已存在相同的版本号")


def create_app(db: Session, data) -> dict:
    """新建应用实体（不创建版本）；App ID / 应用编码由平台生成，安装包在版本页上传."""
    bundle_name = (data.bundle_name or "").strip()
    if not bundle_name:
        raise HTTPException(status_code=400, detail="请填写 Bundle Name")
    if db.query(AppBase).filter(AppBase.bundle_name == bundle_name).first():
        raise HTTPException(status_code=400, detail="Bundle Name 已存在")

    now = local_now()
    pk = snowflake_id()
    # 端侧 AppIdentifier：云侧雪花 ID 字符串，全局唯一
    biz_app_id = str(pk)
    # 应用编码：优先用 Bundle Name；若与历史编码冲突则加雪花后缀
    code = bundle_name
    if len(code) > 64:
        code = code[:64]
    if db.query(AppBase).filter(AppBase.app_code == code).first():
        suffix = str(pk)[-8:]
        code = f"{bundle_name[:55]}_{suffix}"[:64]

    app = AppBase(
        id=pk,
        app_name=data.app_name.strip(),
        app_code=code,
        app_id=biz_app_id,
        bundle_name=bundle_name,
        description=data.description,
        status=1,  # 新建默认上架；上下架改由列表操作
        create_time=now,
        update_time=now,
    )
    db.add(app)
    db.commit()
    return get_app(db, pk)


def _has_published_version(db: Session, app_id: int) -> bool:
    """是否存在已发布版本（version.status == 2）."""
    return (
        db.query(AppVersion.id)
        .filter(AppVersion.app_id == app_id, AppVersion.status == 2)
        .first()
        is not None
    )


def update_app(db: Session, app_id: int, data) -> dict:
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    if data.app_name is not None:
        app.app_name = data.app_name.strip()
    if data.description is not None:
        app.description = data.description
    if data.status is not None:
        new_status = int(data.status)
        if new_status not in (0, 1):
            raise HTTPException(status_code=400, detail="应用状态无效")
        old_status = int(app.status or 0)
        if new_status != old_status:
            if new_status == 1:
                # 上架：须至少有一个已发布版本
                if not _has_published_version(db, app_id):
                    raise HTTPException(
                        status_code=400,
                        detail="当前没有已发布的版本，请先发布至少一个版本后再上架",
                    )
            else:
                # 下架：须没有任何已发布版本
                if _has_published_version(db, app_id):
                    raise HTTPException(
                        status_code=400,
                        detail="请先下架该应用的全部已发布版本，再下架应用",
                    )
        app.status = new_status
    if data.app_icon is not None:
        app.app_icon = data.app_icon
    app.update_time = local_now()
    db.commit()
    return get_app(db, app_id)


def delete_app(db: Session, app_id: int) -> None:
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    # 删除须先下架（下架本身已要求无已发布版本）
    if int(app.status or 0) == 1:
        raise HTTPException(
            status_code=400,
            detail="应用处于上架状态，请先下架后再删除",
        )
    versions = db.query(AppVersion).filter(AppVersion.app_id == app_id).all()
    for v in versions:
        if v.file_path:
            path = DATA_DIR / v.file_path
            if path.is_file():
                path.unlink(missing_ok=True)
    db.query(AppVersion).filter(AppVersion.app_id == app_id).delete()
    db.delete(app)
    db.commit()
    # 清理目录
    app_dir = UPLOAD_ROOT / str(app_id)
    if app_dir.exists():
        shutil.rmtree(app_dir, ignore_errors=True)


def list_versions(db: Session, app_id: int) -> list[dict]:
    get_app(db, app_id)
    rows = (
        db.query(AppVersion)
        .filter(AppVersion.app_id == app_id)
        .order_by(AppVersion.id.desc())
        .all()
    )
    return [_version_out(v) for v in rows]


def get_version(db: Session, app_id: int, version_id: int) -> dict:
    v = (
        db.query(AppVersion)
        .filter(AppVersion.id == version_id, AppVersion.app_id == app_id)
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="应用版本不存在")
    return _version_out(v)


def create_version(db: Session, app_id: int, data) -> dict:
    get_app(db, app_id)
    version_name = data.version_name.strip()
    version_code = data.version_code.strip()
    _ensure_unique_version_fields(
        db, app_id=app_id, version_name=version_name, version_code=version_code
    )
    now = local_now()
    vid = snowflake_id()
    # 新建默认已发布；若调用方显式传 status 仍尊重（兼容旧客户端）
    status = int(data.status) if data.status is not None else 2
    if status not in (2, 3):
        status = 2
    db.add(
        AppVersion(
            id=vid,
            app_id=app_id,
            version_name=version_name,
            version_code=version_code,
            status=status,
            publish_time=now if status == 2 else None,
            create_time=now,
            update_time=now,
        )
    )
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if app:
        app.update_time = now
    db.commit()
    return get_version(db, app_id, vid)


def _parse_policy_param(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _url_hits_version_pk(url: str, version_pk: str) -> bool:
    """bundleDownloadUrl 是否指向本版本主键路径 /versions/{pk}."""
    marker = f"/versions/{version_pk}"
    idx = (url or "").find(marker)
    if idx < 0:
        return False
    end = idx + len(marker)
    if end >= len(url):
        return True
    # 避免 /versions/123 误匹配 /versions/1234
    return url[end] in "/?\""


def _current_apps_entry_hits_version(
    entry: Any, *, app: AppBase, version: AppVersion
) -> bool:
    """currentApps 条目是否占用本版本（仅取消发布校验用）."""
    if not isinstance(entry, dict):
        return False
    version_pk = str(version.id)
    url = str(entry.get("bundleDownloadUrl") or "")
    if _url_hits_version_pk(url, version_pk):
        return True

    entry_ver = str(entry.get("version") or "").strip()
    if entry_ver != str(version.version_name or "").strip():
        return False
    # 版本号须配合 appId / bundleName 消歧，单独出现不算占用
    app_id = str(app.app_id or "").strip()
    bundle = str(app.bundle_name or "").strip()
    entry_app = str(entry.get("appId") or "").strip()
    entry_bundle = str(entry.get("bundleName") or "").strip()
    if app_id and entry_app == app_id:
        return True
    if bundle and entry_bundle == bundle:
        return True
    return False


def _assert_version_not_referenced_in_app_management(
    db: Session, app: AppBase, version: AppVersion
) -> None:
    """下架前：初始策略 / 设备预期快照的 APP_MANAGEMENT.currentApps 不得仍指向本版本.

    命中时仅返回模糊提示，不暴露具体引用位置。
    """
    busy_msg = "该版本正在使用中，暂时无法下架"

    # 1) 初始策略模板
    items = (
        db.query(InitialPolicyItem)
        .filter(InitialPolicyItem.policy_code == POLICY_APP_MANAGEMENT)
        .all()
    )
    for item in items:
        param = _parse_policy_param(item.param_json)
        apps = param.get("currentApps")
        if not isinstance(apps, list):
            continue
        for entry in apps:
            if _current_apps_entry_hits_version(entry, app=app, version=version):
                raise HTTPException(status_code=400, detail=busy_msg)

    # 2) 设备预期快照：先 SQL LIKE 收窄，再按 currentApps 规则确认
    version_pk = str(version.id)
    candidates = (
        db.query(DevicePolicyExpected)
        .filter(
            DevicePolicyExpected.policy_code == POLICY_APP_MANAGEMENT,
            DevicePolicyExpected.param_json.like(f"%/versions/{version_pk}%"),
        )
        .all()
    )
    for row in candidates:
        param = _parse_policy_param(row.param_json)
        apps = param.get("currentApps")
        if not isinstance(apps, list):
            continue
        for entry in apps:
            if _current_apps_entry_hits_version(entry, app=app, version=version):
                raise HTTPException(status_code=400, detail=busy_msg)


def update_version(db: Session, app_id: int, version_id: int, data) -> dict:
    v = (
        db.query(AppVersion)
        .filter(AppVersion.id == version_id, AppVersion.app_id == app_id)
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="应用版本不存在")
    next_name = v.version_name
    next_code = v.version_code
    if data.version_name is not None:
        next_name = data.version_name.strip()
    if data.version_code is not None:
        next_code = data.version_code.strip()
    if data.version_name is not None or data.version_code is not None:
        _ensure_unique_version_fields(
            db,
            app_id=app_id,
            version_name=next_name,
            version_code=next_code,
            exclude_id=version_id,
        )
        v.version_name = next_name
        v.version_code = next_code
    if data.status is not None:
        new_status = int(data.status)
        old_status = int(v.status or 0)
        # 取消发布（离开已发布）：校验 currentApps 是否仍引用本版本
        if old_status == 2 and new_status != 2:
            app = db.query(AppBase).filter(AppBase.id == app_id).first()
            if not app:
                raise HTTPException(status_code=404, detail="应用不存在")
            _assert_version_not_referenced_in_app_management(db, app, v)
        v.status = new_status
        if v.status == 2 and not v.publish_time:
            v.publish_time = local_now()
    v.update_time = local_now()
    db.commit()
    return get_version(db, app_id, version_id)


def delete_version(db: Session, app_id: int, version_id: int) -> None:
    v = (
        db.query(AppVersion)
        .filter(AppVersion.id == version_id, AppVersion.app_id == app_id)
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="应用版本不存在")
    # 仅下架状态（status=3）可删
    if int(v.status or 0) != 3:
        raise HTTPException(
            status_code=400,
            detail="请先下架该版本后再删除",
        )
    if v.file_path:
        path = DATA_DIR / v.file_path
        if path.is_file():
            path.unlink(missing_ok=True)
    db.delete(v)
    db.commit()


def _apply_package_file(v: AppVersion, dest: Path, *, safe_name: str | None = None) -> None:
    """用本地文件刷新版本包元数据（路径相对 DATA_DIR）。"""
    name = safe_name or dest.name
    md5 = hashlib.md5()
    size = 0
    with dest.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            md5.update(chunk)
    if v.file_path:
        old = DATA_DIR / v.file_path
        if old.is_file() and old.resolve() != dest.resolve():
            old.unlink(missing_ok=True)
    v.file_name = name
    v.file_path = dest.relative_to(DATA_DIR).as_posix()
    v.file_size = size
    v.file_md5 = md5.hexdigest()
    v.update_time = local_now()


async def upload_package(
    db: Session,
    app_id: int,
    version_id: int,
    file: UploadFile,
    *,
    resign: bool = False,
) -> dict:
    v = (
        db.query(AppVersion)
        .filter(AppVersion.id == version_id, AppVersion.app_id == app_id)
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="应用版本不存在")
    filename = file.filename or "package.hap"
    _ensure_hap(filename)

    dest_dir = UPLOAD_ROOT / str(app_id) / str(version_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    # 统一存为原文件名（仅保留 basename）
    safe_name = Path(filename).name
    dest = dest_dir / safe_name

    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    _apply_package_file(v, dest, safe_name=safe_name)
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if app:
        app.update_time = local_now()
    db.commit()

    if resign:
        return resign_package(db, app_id, version_id)
    return get_version(db, app_id, version_id)


def resign_package(db: Session, app_id: int, version_id: int) -> dict:
    """模式 2 hapResign：对已上传安装包解包并用平台密钥重签，覆盖版本包."""
    from app.services import store_sign

    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    bundle = (app.bundle_name or "").strip()
    if not bundle:
        raise HTTPException(status_code=400, detail="请先完善应用 Bundle Name")

    v = (
        db.query(AppVersion)
        .filter(AppVersion.id == version_id, AppVersion.app_id == app_id)
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="应用版本不存在")
    if not v.file_path:
        raise HTTPException(status_code=400, detail="该版本尚未上传安装包")
    src = DATA_DIR / v.file_path
    if not src.is_file():
        raise HTTPException(status_code=400, detail="安装包文件不存在")

    work = store_sign.sign_dir() / "work" / "resign" / str(app_id) / str(version_id) / uuid.uuid4().hex
    dest_dir = UPLOAD_ROOT / str(app_id) / str(version_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_name = Path(v.file_name or src.name).stem
    if out_name.startswith("unsign-"):
        out_name = out_name[len("unsign-") :]
    out_hap = dest_dir / f"{out_name}-signed.hap"
    try:
        store_sign.hap_resign(
            src,
            bundle_name=bundle,
            work_dir=work,
            out_hap=out_hap,
            version_code=v.version_code or "1",
            version_name=v.version_name or "1.0.0",
        )
        _apply_package_file(v, out_hap, safe_name=out_hap.name)
        app.update_time = local_now()
        db.commit()
        return get_version(db, app_id, version_id)
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def upload_icon(db: Session, app_id: int, file: UploadFile) -> dict:
    """上传应用图标，写入 app_icon 相对路径."""
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    filename = file.filename or "icon.png"
    ext = _ensure_icon(filename)

    dest_dir = UPLOAD_ROOT / str(app_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"icon{ext}"

    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > ICON_MAX_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="图标文件不能超过 2MB")
            out.write(chunk)

    # 删除同目录下其它扩展名的旧图标
    if app.app_icon:
        old = DATA_DIR / app.app_icon
        if old.is_file() and old.resolve() != dest.resolve():
            old.unlink(missing_ok=True)
    for leftover in dest_dir.glob("icon.*"):
        if leftover.resolve() != dest.resolve():
            leftover.unlink(missing_ok=True)

    rel = dest.relative_to(DATA_DIR).as_posix()
    app.app_icon = rel
    app.update_time = local_now()
    db.commit()
    return get_app(db, app_id)


def get_icon_path(db: Session, app_id: int) -> tuple[Path, str]:
    """返回已上传图标的本地路径与下载文件名."""
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    if not app.app_icon:
        raise HTTPException(status_code=404, detail="尚未上传应用图标")
    path = DATA_DIR / app.app_icon
    if not path.is_file():
        raise HTTPException(status_code=404, detail="图标文件不存在")
    return path, path.name


def clear_icon(db: Session, app_id: int) -> dict:
    """清除已上传图标，恢复默认图标显示."""
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    if app.app_icon:
        old = DATA_DIR / app.app_icon
        if old.is_file():
            old.unlink(missing_ok=True)
        app.app_icon = None
        app.update_time = local_now()
        db.commit()
    return get_app(db, app_id)


def list_app_installs(
    db: Session,
    app_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
) -> dict:
    """应用安装情况：设备总量 / 已安装数 + 已安装明细."""
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")

    device_total = db.query(Device).count()
    installed_count = (
        db.query(DeviceAppInstalled).filter(DeviceAppInstalled.app_id == app_id).count()
    )
    not_installed = max(device_total - installed_count, 0)
    rate = round(installed_count * 100.0 / device_total, 1) if device_total else 0.0

    q = (
        db.query(DeviceAppInstalled, Device, AppVersion, SysMember, SysDepartment)
        .join(Device, Device.id == DeviceAppInstalled.device_id)
        .outerjoin(AppVersion, AppVersion.id == DeviceAppInstalled.app_version_id)
        .outerjoin(SysMember, SysMember.id == Device.member_id)
        .outerjoin(SysDepartment, SysDepartment.id == SysMember.department_id)
        .filter(DeviceAppInstalled.app_id == app_id)
    )
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            (Device.sn.like(like))
            | (SysMember.name.like(like))
            | (SysDepartment.path.like(like))
            | (SysDepartment.name.like(like))
        )
    total = q.count()
    rows = (
        q.order_by(DeviceAppInstalled.install_time.desc(), DeviceAppInstalled.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    install_type_map = {1: "指令下发", 2: "用户安装"}
    device_status_map = {1: "在线", 2: "离线", 3: "已挂失"}
    items = []
    for inst, device, ver, member, dept in rows:
        status = int(device.status or 2) if device else 2
        items.append(
            {
                "id": str(inst.id),
                "device_id": str(device.id) if device else "",
                "device_sn": device.sn if device else "",
                "member_name": (member.name if member else "") or "",
                "department_path": (
                    (dept.path if dept else "") or (dept.name if dept else "") or ""
                ),
                "device_status": status,
                "device_status_label": device_status_map.get(status, "离线"),
                "version_id": str(inst.app_version_id),
                "version_name": (ver.version_name if ver else "") or "—",
                "version_code": (ver.version_code if ver else "") or "",
                "install_type": int(inst.install_type)
                if inst.install_type is not None
                else None,
                "install_type_label": install_type_map.get(
                    int(inst.install_type or 0), "—"
                ),
                "install_time": _fmt(inst.install_time),
            }
        )

    return {
        "summary": {
            "device_total": device_total,
            "installed_count": installed_count,
            "not_installed_count": not_installed,
            "install_rate": rate,
        },
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
