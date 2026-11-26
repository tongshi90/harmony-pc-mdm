"""我的应用 · Profile（复用商店证书 t_store_cert + store_sign）."""

from __future__ import annotations

import shutil
from datetime import date, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models.app_pkg import AppBase, AppProfile
from app.models.store import StoreCert
from app.services import store_sign
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

PROFILE_MAX_PER_APP = 10
UPLOAD_ROOT = DATA_DIR / "uploads" / "app"


def _fmt_dt(v) -> str:
    if not v:
        return ""
    return v.strftime("%Y-%m-%d %H:%M:%S") if hasattr(v, "strftime") else str(v)


def _fmt_date(v) -> str:
    if not v:
        return ""
    return v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v)


def _safe_filename(name: str) -> str:
    base = Path(name or "profile.p7b").name
    return "".join(c if c.isalnum() or c in "._-+()[] " else "_" for c in base)[:180] or "profile.p7b"


def _rel_path(path: Path) -> str:
    try:
        return str(path.relative_to(DATA_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _get_app(db: Session, app_id: int) -> AppBase:
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    return app


def _profile_out(p: AppProfile) -> dict:
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
            f"/platform/app/{p.app_id}/profiles/{p.id}/file" if has_file else ""
        ),
        "expiration_date": _fmt_date(p.expiration_date),
        "create_time": _fmt_dt(p.create_time),
        "update_time": _fmt_dt(p.update_time),
    }


def list_profiles(db: Session, app_id: int) -> list[dict]:
    _get_app(db, app_id)
    rows = (
        db.query(AppProfile)
        .filter(AppProfile.app_id == app_id, AppProfile.is_delete == 0)
        .order_by(AppProfile.id.desc())
        .all()
    )
    return [_profile_out(r) for r in rows]


def add_profile(db: Session, app_id: int, *, profile_name: str, cert_id: int | str) -> dict:
    app = _get_app(db, app_id)
    bundle = (app.bundle_name or "").strip()
    if not bundle:
        raise HTTPException(
            status_code=400,
            detail="请先完善应用 Bundle Name，再生成 Profile",
        )

    pname = (profile_name or "").strip()
    if not pname:
        raise HTTPException(status_code=400, detail="请填写 Profile 名称")
    if len(pname) > 128:
        raise HTTPException(status_code=400, detail="Profile 名称过长")

    cnt = (
        db.query(AppProfile)
        .filter(AppProfile.app_id == app_id, AppProfile.is_delete == 0)
        .count()
    )
    if cnt >= PROFILE_MAX_PER_APP:
        raise HTTPException(
            status_code=400,
            detail=f"每个应用最多 {PROFILE_MAX_PER_APP} 个 Profile",
        )

    try:
        cid = int(cert_id)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail="证书 ID 无效") from e

    cert = (
        db.query(StoreCert)
        .filter(StoreCert.id == cid, StoreCert.is_delete == 0)
        .first()
    )
    if not cert:
        raise HTTPException(status_code=404, detail="证书不存在")
    if not (cert.app_cert or "").strip():
        raise HTTPException(
            status_code=400,
            detail="该证书未解析到应用证书 PEM，请先在「证书」中上传/签发",
        )

    status = store_sign.check_sign_tools(for_profile=True)
    if not status.ready:
        raise HTTPException(status_code=400, detail=status.message)

    profile_id = snowflake_id()
    work = store_sign.sign_dir() / "work" / "app" / str(app.id) / f"profile_{profile_id}"
    try:
        provision = store_sign.build_provision_for_app(
            bundle_name=bundle,
            app_cert_pem=cert.app_cert or "",
        )
        p7b_path = store_sign.sign_profile_p7b(
            provision, work_dir=work, out_name=f"{pname}.p7b"
        )
        dest_dir = UPLOAD_ROOT / str(app.id) / "profiles" / str(profile_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = _safe_filename(f"{pname}.p7b")
        dest = dest_dir / safe
        shutil.copy2(p7b_path, dest)
        file_size = dest.stat().st_size
    finally:
        shutil.rmtree(work, ignore_errors=True)

    now = local_now()
    row = AppProfile(
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
        db.query(AppProfile)
        .filter(
            AppProfile.id == profile_id,
            AppProfile.app_id == app_id,
            AppProfile.is_delete == 0,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Profile 不存在")
    if row.file_path:
        path = DATA_DIR / row.file_path
        if path.is_file():
            path.unlink(missing_ok=True)
    row.is_delete = 1
    row.update_time = local_now()
    db.commit()


def get_profile_file_path(db: Session, app_id: int, profile_id: int) -> tuple[Path, str]:
    _get_app(db, app_id)
    row = (
        db.query(AppProfile)
        .filter(
            AppProfile.id == profile_id,
            AppProfile.app_id == app_id,
            AppProfile.is_delete == 0,
        )
        .first()
    )
    if not row or not row.file_path:
        raise HTTPException(status_code=404, detail="Profile 文件不存在")
    path = DATA_DIR / row.file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Profile 文件不存在")
    return path, row.file_name or path.name
