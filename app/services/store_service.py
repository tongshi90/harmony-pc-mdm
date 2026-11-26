"""应用商店调试：证书 + Profile + 应用/版本（与 MDM 应用仓库无关）."""

from __future__ import annotations

import hashlib
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models.store import StoreApp, StoreAppVersion, StoreCert, StoreProfile
from app.schemas.store import StoreAppCreate, StoreAppUpdate, StoreProfileCreate
from app.services import store_sign
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

UPLOAD_ROOT = DATA_DIR / "uploads" / "store"
CERT_MAX_COUNT = 3
PROFILE_MAX_PER_APP = 3
CERT_EXTS = {".csr", ".cer", ".pem", ".crt"}
PKG_EXTS = {".app", ".hap", ".sap"}
ICON_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
ICON_MAX_BYTES = 2 * 1024 * 1024
_PEM_RE = re.compile(
    r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
    re.DOTALL,
)


def _fmt_dt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _fmt_date(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _safe_filename(name: str) -> str:
    base = Path(name or "file").name
    return re.sub(r"[^\w.\-()\u4e00-\u9fff]+", "_", base) or "file"


def _rel_path(path: Path) -> str:
    return path.relative_to(DATA_DIR).as_posix()


def _unlink_rel(rel: str | None) -> None:
    if not rel:
        return
    path = DATA_DIR / rel
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _extract_pem(raw: bytes) -> str | None:
    """从 cer/pem 文本中取第一段证书 PEM；二进制/CSR 则返回 None."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except Exception:  # noqa: BLE001
            return None
    m = _PEM_RE.search(text)
    if not m:
        return None
    return m.group(0).replace("\r\n", "\n").strip() + "\n"


def _cert_out(c: StoreCert) -> dict:
    return {
        "id": str(c.id),
        "cert_name": c.cert_name,
        "cert_type": int(c.cert_type or 1),
        "cert_type_label": "发布证书",
        "file_name": c.file_name or "",
        "file_size": c.file_size,
        "has_file": bool(c.file_path),
        "has_pem": bool(c.app_cert),
        "download_url": (
            f"/platform/store/certs/{c.id}/file" if c.file_path else ""
        ),
        "expiration_date": _fmt_date(c.expiration_date),
        "create_time": _fmt_dt(c.create_time),
        "update_time": _fmt_dt(c.update_time),
    }


def _version_out(v: StoreAppVersion) -> dict:
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
            f"/platform/store/apps/{v.app_id}/versions/{v.id}/package"
            if has_pkg
            else ""
        ),
        "create_time": _fmt_dt(v.create_time),
        "update_time": _fmt_dt(v.update_time),
    }


def _profile_out(p: StoreProfile) -> dict:
    has_file = bool(p.file_path)
    return {
        "id": str(p.id),
        "app_id": str(p.app_id),
        "cert_id": str(p.cert_id),
        "cert_name": p.cert_name or "",
        "profile_name": p.profile_name,
        "profile_status": int(p.profile_status or 1),
        "profile_status_label": "生效" if int(p.profile_status or 1) == 1 else "失效",
        "file_name": p.file_name or "",
        "file_size": p.file_size,
        "has_file": has_file,
        "download_url": (
            f"/platform/store/apps/{p.app_id}/profiles/{p.id}/file"
            if has_file
            else ""
        ),
        "expiration_date": _fmt_date(p.expiration_date),
        "create_time": _fmt_dt(p.create_time),
        "update_time": _fmt_dt(p.update_time),
    }


def _app_out(db: Session, app: StoreApp, *, detail: bool = False) -> dict:
    versions = (
        db.query(StoreAppVersion)
        .filter(
            StoreAppVersion.app_id == app.id,
            StoreAppVersion.is_delete == 0,
        )
        .order_by(StoreAppVersion.id.desc())
        .all()
    )
    profiles = (
        db.query(StoreProfile)
        .filter(
            StoreProfile.app_id == app.id,
            StoreProfile.is_delete == 0,
        )
        .order_by(StoreProfile.id.desc())
        .all()
    )
    latest = versions[0] if versions else None
    data = {
        "id": str(app.id),
        "app_name": app.app_name,
        "package_name": app.package_name,
        "description": app.description or "",
        "has_icon": bool(app.icon_path),
        "icon_url": (
            f"/platform/store/apps/{app.id}/icon" if app.icon_path else ""
        ),
        "version_count": len(versions),
        "profile_count": len(profiles),
        "latest_version": latest.version_name if latest else "",
        "create_time": _fmt_dt(app.create_time),
        "update_time": _fmt_dt(app.update_time),
    }
    if detail:
        data["versions"] = [_version_out(v) for v in versions]
        data["profiles"] = [_profile_out(p) for p in profiles]
    return data


def _get_app(db: Session, app_id: int) -> StoreApp:
    app = (
        db.query(StoreApp)
        .filter(StoreApp.id == app_id, StoreApp.is_delete == 0)
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    return app


def count_active_certs(db: Session) -> int:
    return (
        db.query(StoreCert).filter(StoreCert.is_delete == 0).count()
    )


# ---------- 证书 ----------


def list_certs(db: Session) -> list[dict]:
    rows = (
        db.query(StoreCert)
        .filter(StoreCert.is_delete == 0)
        .order_by(StoreCert.create_time.desc(), StoreCert.id.desc())
        .all()
    )
    return [_cert_out(r) for r in rows]


async def add_cert(
    db: Session, *, cert_name: str, file: UploadFile
) -> dict:
    """新增证书。

    - 上传 .csr：对齐 hm-appstore，调用 keytool 基于 OpenHarmony.p12 签发 .cer
    - 上传 .cer/.pem/.crt：直接落盘并解析叶子证书 PEM（调试用）
    """
    name = (cert_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写证书名称")
    if len(name) > 128:
        raise HTTPException(status_code=400, detail="证书名称过长")
    if count_active_certs(db) >= CERT_MAX_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"证书数量已达上限（最多 {CERT_MAX_COUNT} 张），请先删除后再新增",
        )

    raw_name = file.filename or "cert.cer"
    ext = Path(raw_name).suffix.lower()
    if ext not in CERT_EXTS:
        raise HTTPException(
            status_code=400,
            detail="证书文件仅支持 .csr / .cer / .pem / .crt",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="证书文件为空")

    cert_id = snowflake_id()
    dest_dir = UPLOAD_ROOT / "certs" / str(cert_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    app_cert: str | None = None
    if ext == ".csr":
        # 签发工作目录放在 data/sign/{tenant-like}/，与原项目 certDir + tenant 对齐
        issue_dir = store_sign.sign_dir() / "issued" / str(cert_id)
        issued_bytes, leaf_pem = store_sign.issue_cer_from_csr(
            content, cert_name=name, out_dir=issue_dir
        )
        safe = _safe_filename(f"{name}.cer")
        dest = dest_dir / safe
        dest.write_bytes(issued_bytes)
        content = issued_bytes
        app_cert = leaf_pem
    else:
        safe = _safe_filename(raw_name)
        dest = dest_dir / safe
        dest.write_bytes(content)
        app_cert = _extract_pem(content)

    now = local_now()
    row = StoreCert(
        id=cert_id,
        cert_name=name,
        cert_type=1,
        file_name=safe,
        file_path=_rel_path(dest),
        file_size=len(content),
        app_cert=app_cert,
        expiration_date=date.today() + timedelta(days=365 * 4),
        is_delete=0,
        create_time=now,
        update_time=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _cert_out(row)


def delete_cert(db: Session, cert_id: int) -> None:
    row = (
        db.query(StoreCert)
        .filter(StoreCert.id == cert_id, StoreCert.is_delete == 0)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="证书不存在")
    _unlink_rel(row.file_path)
    # 尝试清空目录
    if row.file_path:
        try:
            parent = (DATA_DIR / row.file_path).parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass
    row.is_delete = 1
    row.update_time = local_now()
    db.commit()


def get_cert_file_path(db: Session, cert_id: int) -> tuple[Path, str]:
    row = (
        db.query(StoreCert)
        .filter(StoreCert.id == cert_id, StoreCert.is_delete == 0)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="证书不存在")
    if not row.file_path:
        raise HTTPException(status_code=404, detail="证书文件不存在")
    path = DATA_DIR / row.file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="证书文件不存在")
    return path, row.file_name or path.name


# ---------- 应用 ----------


def list_apps(
    db: Session,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 12,
) -> dict:
    q = db.query(StoreApp).filter(StoreApp.is_delete == 0)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            (StoreApp.app_name.like(like)) | (StoreApp.package_name.like(like))
        )
    total = q.count()
    rows = (
        q.order_by(StoreApp.update_time.desc(), StoreApp.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_app_out(db, r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "cert_count": count_active_certs(db),
    }


def get_app(db: Session, app_id: int) -> dict:
    return _app_out(db, _get_app(db, app_id), detail=True)


def create_app(db: Session, body: StoreAppCreate) -> dict:
    pkg = (body.package_name or "").strip()
    name = (body.app_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写应用名称")
    if not pkg:
        raise HTTPException(status_code=400, detail="请填写包名")
    exists = (
        db.query(StoreApp)
        .filter(StoreApp.package_name == pkg, StoreApp.is_delete == 0)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="包名已存在")
    now = local_now()
    # package_name 有全局唯一约束；软删除行仍占坑。同名已删记录则复活复用，避免 IntegrityError→500 非 JSON
    deleted = (
        db.query(StoreApp)
        .filter(StoreApp.package_name == pkg, StoreApp.is_delete == 1)
        .first()
    )
    if deleted:
        deleted.app_name = name
        deleted.description = (body.description or "").strip() or None
        deleted.icon_path = None
        deleted.is_delete = 0
        deleted.update_time = now
        db.commit()
        db.refresh(deleted)
        return _app_out(db, deleted, detail=True)
    app = StoreApp(
        id=snowflake_id(),
        app_name=name,
        package_name=pkg,
        description=(body.description or "").strip() or None,
        is_delete=0,
        create_time=now,
        update_time=now,
    )
    db.add(app)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        # 并发等极端情况仍可能撞唯一索引
        raise HTTPException(
            status_code=400, detail=f"包名不可用（可能已被占用）：{e}"
        ) from e
    db.refresh(app)
    return _app_out(db, app, detail=True)


def update_app(db: Session, app_id: int, body: StoreAppUpdate) -> dict:
    app = _get_app(db, app_id)
    if body.app_name is not None:
        name = body.app_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="应用名称不能为空")
        app.app_name = name
    if body.description is not None:
        app.description = body.description.strip() or None
    app.update_time = local_now()
    db.commit()
    db.refresh(app)
    return _app_out(db, app, detail=True)


def delete_app(db: Session, app_id: int) -> None:
    app = _get_app(db, app_id)
    ver_cnt = (
        db.query(StoreAppVersion)
        .filter(
            StoreAppVersion.app_id == app_id,
            StoreAppVersion.is_delete == 0,
        )
        .count()
    )
    if ver_cnt > 0:
        raise HTTPException(
            status_code=400,
            detail="该应用仍有版本，请先删除全部版本后再删应用",
        )
    # 级联逻辑删除 Profile，并清理 p7b 文件
    profiles = (
        db.query(StoreProfile)
        .filter(StoreProfile.app_id == app_id, StoreProfile.is_delete == 0)
        .all()
    )
    now = local_now()
    for p in profiles:
        _unlink_rel(p.file_path)
        p.is_delete = 1
        p.update_time = now
    _unlink_rel(app.icon_path)
    app.is_delete = 1
    app.update_time = now
    db.commit()


async def upload_icon(
    db: Session, app_id: int, file: UploadFile
) -> dict:
    app = _get_app(db, app_id)
    raw_name = file.filename or "icon.png"
    ext = Path(raw_name).suffix.lower()
    if ext not in ICON_EXTS:
        raise HTTPException(
            status_code=400,
            detail="图标仅支持 png / jpg / jpeg / webp / gif / svg",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="图标文件为空")
    if len(content) > ICON_MAX_BYTES:
        raise HTTPException(status_code=400, detail="图标不能超过 2MB")

    dest_dir = UPLOAD_ROOT / "apps" / str(app_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"icon{ext}"
    if app.icon_path:
        _unlink_rel(app.icon_path)
    dest.write_bytes(content)
    app.icon_path = _rel_path(dest)
    app.update_time = local_now()
    db.commit()
    db.refresh(app)
    return _app_out(db, app)


def get_icon_path(db: Session, app_id: int) -> tuple[Path, str]:
    app = _get_app(db, app_id)
    if not app.icon_path:
        raise HTTPException(status_code=404, detail="未上传图标")
    path = DATA_DIR / app.icon_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="图标文件不存在")
    return path, path.name


# ---------- 版本 ----------


def list_versions(db: Session, app_id: int) -> list[dict]:
    _get_app(db, app_id)
    rows = (
        db.query(StoreAppVersion)
        .filter(
            StoreAppVersion.app_id == app_id,
            StoreAppVersion.is_delete == 0,
        )
        .order_by(StoreAppVersion.id.desc())
        .all()
    )
    return [_version_out(v) for v in rows]


async def create_version_with_package(
    db: Session,
    app_id: int,
    *,
    version_name: str,
    version_code: str,
    file: UploadFile,
) -> dict:
    app = _get_app(db, app_id)
    if count_active_certs(db) < 1:
        raise HTTPException(
            status_code=400,
            detail="请先在证书管理中添加签名证书！",
        )

    vname = (version_name or "").strip()
    vcode = (version_code or "").strip()
    if not vname:
        raise HTTPException(status_code=400, detail="请填写版本名称")
    if not vcode:
        raise HTTPException(status_code=400, detail="请填写版本号")

    raw_name = file.filename or "package.app"
    ext = Path(raw_name).suffix.lower()
    if ext not in PKG_EXTS:
        raise HTTPException(
            status_code=400,
            detail="安装包仅支持 .app / .hap / .sap",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="安装包文件为空")

    version_id = snowflake_id()
    safe = _safe_filename(raw_name)
    dest_dir = (
        UPLOAD_ROOT / "apps" / str(app.id) / "versions" / str(version_id)
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    dest.write_bytes(content)
    md5 = hashlib.md5(content).hexdigest()

    now = local_now()
    row = StoreAppVersion(
        id=version_id,
        app_id=app.id,
        version_name=vname,
        version_code=vcode,
        file_name=safe,
        file_path=_rel_path(dest),
        file_size=len(content),
        file_md5=md5,
        is_delete=0,
        create_time=now,
        update_time=now,
    )
    db.add(row)
    app.update_time = now
    db.commit()
    db.refresh(row)
    return _version_out(row)


def delete_version(db: Session, app_id: int, version_id: int) -> None:
    _get_app(db, app_id)
    row = (
        db.query(StoreAppVersion)
        .filter(
            StoreAppVersion.id == version_id,
            StoreAppVersion.app_id == app_id,
            StoreAppVersion.is_delete == 0,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="版本不存在")
    _unlink_rel(row.file_path)
    if row.file_path:
        try:
            parent = (DATA_DIR / row.file_path).parent
            if parent.is_dir():
                shutil.rmtree(parent, ignore_errors=True)
        except OSError:
            pass
    row.is_delete = 1
    row.update_time = local_now()
    db.commit()


def get_package_path(
    db: Session, app_id: int, version_id: int
) -> tuple[Path, str]:
    row = (
        db.query(StoreAppVersion)
        .filter(
            StoreAppVersion.id == version_id,
            StoreAppVersion.app_id == app_id,
            StoreAppVersion.is_delete == 0,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="版本不存在")
    if not row.file_path:
        raise HTTPException(status_code=404, detail="该版本尚未上传安装包")
    path = DATA_DIR / row.file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="安装包文件不存在")
    return path, row.file_name or path.name


# ---------- Profile ----------


def list_profiles(db: Session, app_id: int) -> list[dict]:
    _get_app(db, app_id)
    rows = (
        db.query(StoreProfile)
        .filter(
            StoreProfile.app_id == app_id,
            StoreProfile.is_delete == 0,
        )
        .order_by(StoreProfile.id.desc())
        .all()
    )
    return [_profile_out(r) for r in rows]


def add_profile(
    db: Session, app_id: int, body: StoreProfileCreate
) -> dict:
    """对齐 InfoProfileServiceImpl.addProfile：写 provision JSON → sign-profile → 落盘 p7b。"""
    app = _get_app(db, app_id)
    pname = (body.profile_name or "").strip()
    if not pname:
        raise HTTPException(status_code=400, detail="请填写 Profile 名称")
    if len(pname) > 128:
        raise HTTPException(status_code=400, detail="Profile 名称过长")

    cnt = (
        db.query(StoreProfile)
        .filter(
            StoreProfile.app_id == app_id,
            StoreProfile.is_delete == 0,
        )
        .count()
    )
    if cnt >= PROFILE_MAX_PER_APP:
        raise HTTPException(
            status_code=400,
            detail=f"每个应用最多 {PROFILE_MAX_PER_APP} 个 Profile",
        )

    try:
        cert_id = int(body.cert_id)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail="证书 ID 无效") from e
    cert = (
        db.query(StoreCert)
        .filter(StoreCert.id == cert_id, StoreCert.is_delete == 0)
        .first()
    )
    if not cert:
        raise HTTPException(status_code=404, detail="证书不存在")
    if not (cert.app_cert or "").strip():
        raise HTTPException(
            status_code=400,
            detail="该证书未解析到应用证书 PEM，请上传 .cer/.pem 或用 .csr 签发后再试",
        )

    status = store_sign.check_sign_tools(for_profile=True)
    if not status.ready:
        raise HTTPException(status_code=400, detail=status.message)

    profile_id = snowflake_id()
    work = store_sign.sign_dir() / "work" / str(app.id) / f"profile_{profile_id}"
    try:
        provision = store_sign.build_provision_for_app(
            bundle_name=app.package_name,
            app_cert_pem=cert.app_cert or "",
        )
        p7b_path = store_sign.sign_profile_p7b(
            provision, work_dir=work, out_name=f"{pname}.p7b"
        )
        dest_dir = UPLOAD_ROOT / "apps" / str(app.id) / "profiles" / str(profile_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = _safe_filename(f"{pname}.p7b")
        dest = dest_dir / safe
        shutil.copy2(p7b_path, dest)
        file_size = dest.stat().st_size
    finally:
        shutil.rmtree(work, ignore_errors=True)

    now = local_now()
    row = StoreProfile(
        id=profile_id,
        app_id=app.id,
        cert_id=cert.id,
        cert_name=cert.cert_name,
        profile_name=pname,
        profile_status=1,
        expiration_date=date.today() + timedelta(days=365 * 4),
        file_name=safe,
        file_path=_rel_path(dest),
        file_size=file_size,
        is_delete=0,
        create_time=now,
        update_time=now,
    )
    db.add(row)
    app.update_time = now
    db.commit()
    db.refresh(row)
    return _profile_out(row)


def delete_profile(db: Session, app_id: int, profile_id: int) -> None:
    _get_app(db, app_id)
    row = (
        db.query(StoreProfile)
        .filter(
            StoreProfile.id == profile_id,
            StoreProfile.app_id == app_id,
            StoreProfile.is_delete == 0,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Profile 不存在")
    _unlink_rel(row.file_path)
    if row.file_path:
        try:
            parent = (DATA_DIR / row.file_path).parent
            if parent.is_dir():
                shutil.rmtree(parent, ignore_errors=True)
        except OSError:
            pass
    row.is_delete = 1
    row.update_time = local_now()
    db.commit()


def get_profile_file_path(
    db: Session, app_id: int, profile_id: int
) -> tuple[Path, str]:
    row = (
        db.query(StoreProfile)
        .filter(
            StoreProfile.id == profile_id,
            StoreProfile.app_id == app_id,
            StoreProfile.is_delete == 0,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Profile 不存在")
    if not row.file_path:
        raise HTTPException(status_code=404, detail="Profile 文件不存在")
    path = DATA_DIR / row.file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Profile 文件不存在")
    return path, row.file_name or path.name


# ---------- 签名工具状态 ----------


def get_sign_status() -> dict:
    profile = store_sign.check_sign_tools(for_profile=True)
    csr = store_sign.check_sign_tools(for_csr=True)
    resign = store_sign.check_sign_tools(for_resign=True)
    files = {**profile.files, **csr.files, **resign.files}
    missing = sorted(set(profile.missing + csr.missing + resign.missing))
    ready = profile.ready and csr.ready
    return {
        "sign_dir": profile.sign_dir,
        "java_ok": profile.java_ok,
        "issuer": store_sign.issuer(),
        "files": files,
        "missing": missing,
        "profile_ready": profile.ready,
        "csr_ready": csr.ready,
        "resign_ready": resign.ready,
        "ready": ready,
        "message": (
            profile.message
            if not profile.ready
            else (csr.message if not csr.ready else resign.message)
        ),
    }
