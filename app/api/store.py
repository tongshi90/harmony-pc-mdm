"""应用商店调试遗留 API：证书已迁至「应用管理 · 证书」（仍挂本前缀）；应用/版本/Profile 保留供兼容。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log, no_audit
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.schemas.common import ok
from app.schemas.store import StoreAppCreate, StoreAppUpdate, StoreProfileCreate
from app.services import store_service

# 无 router 级菜单依赖：证书走 APP_CERT，遗留应用接口仍走 STORE
router = APIRouter()


# ---------- 签名工具状态 / 证书（「应用管理 · 证书」） ----------


@router.get("/sign-status")
@no_audit
def sign_status(
    _: User = Depends(require_menu(MenuCode.APP_CERT)),
):
    return ok(store_service.get_sign_status())


@router.get("/certs")
def list_certs(
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP_CERT)),
):
    return ok(store_service.list_certs(db))


@router.post("/certs")
@audit_log(module="证书", action="新增证书")
async def add_cert(
    cert_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP_CERT)),
):
    return ok(await store_service.add_cert(db, cert_name=cert_name, file=file))


@router.delete("/certs/{cert_id}")
@audit_log(module="证书", action="删除证书")
def delete_cert(
    cert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP_CERT)),
):
    store_service.delete_cert(db, cert_id)
    return ok()


@router.get("/certs/{cert_id}/file")
@no_audit
def download_cert(
    cert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP_CERT)),
):
    path, filename = store_service.get_cert_file_path(db, cert_id)
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )


# ---------- 遗留：商店应用 / 版本 / Profile（侧栏已隐藏） ----------


@router.get("/apps")
def list_apps(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    return ok(store_service.list_apps(db, keyword, page, page_size))


@router.post("/apps")
@audit_log(module="应用商店调试", action="新建商店应用")
def create_app(
    body: StoreAppCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    return ok(store_service.create_app(db, body))


@router.get("/apps/{app_id}")
def get_app(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    return ok(store_service.get_app(db, app_id))


@router.put("/apps/{app_id}")
@audit_log(module="应用商店调试", action="编辑商店应用")
def update_app(
    app_id: int,
    body: StoreAppUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    return ok(store_service.update_app(db, app_id, body))


@router.delete("/apps/{app_id}")
@audit_log(module="应用商店调试", action="删除商店应用")
def delete_app(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    store_service.delete_app(db, app_id)
    return ok()


@router.post("/apps/{app_id}/icon")
@audit_log(module="应用商店调试", action="上传商店应用图标")
async def upload_icon(
    app_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    return ok(await store_service.upload_icon(db, app_id, file))


@router.get("/apps/{app_id}/icon")
@no_audit
def download_icon(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    path, filename = store_service.get_icon_path(db, app_id)
    suffix = path.suffix.lower()
    media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, filename=filename, media_type=media)


@router.get("/apps/{app_id}/versions")
def list_versions(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    return ok(store_service.list_versions(db, app_id))


@router.post("/apps/{app_id}/versions")
@audit_log(module="应用商店调试", action="上传商店应用版本")
async def create_version(
    app_id: int,
    version_name: str = Form(...),
    version_code: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    return ok(
        await store_service.create_version_with_package(
            db,
            app_id,
            version_name=version_name,
            version_code=version_code,
            file=file,
        )
    )


@router.delete("/apps/{app_id}/versions/{version_id}")
@audit_log(module="应用商店调试", action="删除商店应用版本")
def delete_version(
    app_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    store_service.delete_version(db, app_id, version_id)
    return ok()


@router.get("/apps/{app_id}/versions/{version_id}/package")
@no_audit
def download_package(
    app_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    path, filename = store_service.get_package_path(db, app_id, version_id)
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.get("/apps/{app_id}/profiles")
def list_profiles(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    return ok(store_service.list_profiles(db, app_id))


@router.post("/apps/{app_id}/profiles")
@audit_log(module="应用商店调试", action="新增应用 Profile")
def create_profile(
    app_id: int,
    body: StoreProfileCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    return ok(store_service.add_profile(db, app_id, body))


@router.delete("/apps/{app_id}/profiles/{profile_id}")
@audit_log(module="应用商店调试", action="删除应用 Profile")
def delete_profile(
    app_id: int,
    profile_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    store_service.delete_profile(db, app_id, profile_id)
    return ok()


@router.get("/apps/{app_id}/profiles/{profile_id}/file")
@no_audit
def download_profile(
    app_id: int,
    profile_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.STORE)),
):
    path, filename = store_service.get_profile_file_path(db, app_id, profile_id)
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )
