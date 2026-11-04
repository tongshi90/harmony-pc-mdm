"""平台基础管理 · MDM 应用版本仓库."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log, no_audit
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.schemas.common import ok
from app.schemas.mdm_app import MdmAppVersionCreate, MdmAppVersionUpdate
from app.services import mdm_app_service

router = APIRouter(
    prefix="/mdm-app",
    dependencies=[Depends(require_menu(MenuCode.PLATFORM))],
)

# 设备侧按 bundleDownloadUrl 直链下载（免登录，挂在 /platform/mdm-app）
public_router = APIRouter(prefix="/mdm-app", tags=["MDM应用-安装包下载"])


@router.get("/versions")
def list_versions(
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(mdm_app_service.list_versions(db))


@router.post("/versions")
@audit_log(module="平台基础管理", action="新建 MDM 版本")
def create_version(
    body: MdmAppVersionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(mdm_app_service.create_version(db, body))


@router.get("/versions/{version_id}")
def get_version(
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(mdm_app_service.get_version(db, version_id))


@router.put("/versions/{version_id}")
@audit_log(module="平台基础管理", action="编辑 MDM 版本")
def update_version(
    version_id: int,
    body: MdmAppVersionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(mdm_app_service.update_version(db, version_id, body))


@router.delete("/versions/{version_id}")
@audit_log(module="平台基础管理", action="删除 MDM 版本")
def delete_version(
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    mdm_app_service.delete_version(db, version_id)
    return ok()


@router.post("/versions/{version_id}/package")
@audit_log(module="平台基础管理", action="上传 MDM 安装包")
async def upload_package(
    version_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(await mdm_app_service.upload_package(db, version_id, file))


@public_router.get("/versions/{version_id}/package")
@no_audit
def download_package(
    version_id: int,
    db: Session = Depends(get_db),
):
    """设备侧按 bundleDownloadUrl 下载 MDM HAP（白名单免登录）."""
    path, filename = mdm_app_service.get_package_path(db, version_id)
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )
