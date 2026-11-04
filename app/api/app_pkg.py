from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log, no_audit
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.schemas.app_pkg import (
    AppBatchInstallIn,
    AppBatchUninstallIn,
    AppCreate,
    AppUpdate,
    AppVersionCreate,
    AppVersionUpdate,
)
from app.schemas.common import ok
from app.services import app_batch_service, app_service, department_service

router = APIRouter(dependencies=[Depends(require_menu(MenuCode.APP))])
# 安装包下载：免登录（AuthGuard 已放行；不挂菜单依赖）
public_router = APIRouter()


@router.get("/target-groups")
def list_target_groups(
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    """批量安装/卸载用的分组列表（应用菜单权限即可）."""
    return ok(department_service.list_departments(db, keyword))


@router.get("")
def list_apps(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(app_service.list_apps(db, keyword, page, page_size))


@router.get("/{app_id}")
def get_app(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(app_service.get_app(db, app_id))


@router.post("")
@audit_log(module="应用管理", action="新建应用")
def create_app(
    body: AppCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(app_service.create_app(db, body))


@router.put("/{app_id}")
@audit_log(module="应用管理", action="编辑应用")
def update_app(
    app_id: int,
    body: AppUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(app_service.update_app(db, app_id, body))


@router.delete("/{app_id}")
@audit_log(module="应用管理", action="删除应用")
def delete_app(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    app_service.delete_app(db, app_id)
    return ok()


@router.get("/{app_id}/installs")
def list_app_installs(
    app_id: int,
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    """应用安装情况统计与明细."""
    return ok(
        app_service.list_app_installs(
            db, app_id, page=page, page_size=page_size, keyword=keyword
        )
    )


@router.post("/{app_id}/batch-install")
@audit_log(module="应用管理", action="批量安装")
def batch_install(
    app_id: int,
    body: AppBatchInstallIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_menu(MenuCode.APP)),
):
    """校验并创建任务后立即返回；合并预期快照与 MQTT 在后台执行."""
    data = app_batch_service.batch_install(
        db,
        app_id,
        group_ids=list(body.group_ids or []),
        all_groups=bool(body.all_groups),
        version_id=body.version_id,
        public_base_url=body.public_base_url,
        creator=user,
    )
    background_tasks.add_task(
        app_batch_service.apply_app_batch_task_background, data["id"]
    )
    return ok(data)


@router.post("/{app_id}/batch-uninstall")
@audit_log(module="应用管理", action="批量卸载")
def batch_uninstall(
    app_id: int,
    body: AppBatchUninstallIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_menu(MenuCode.APP)),
):
    """校验并创建任务后立即返回；合并预期快照与 MQTT 在后台执行."""
    data = app_batch_service.batch_uninstall(
        db,
        app_id,
        group_ids=list(body.group_ids or []),
        all_groups=bool(body.all_groups),
        creator=user,
    )
    background_tasks.add_task(
        app_batch_service.apply_app_batch_task_background, data["id"]
    )
    return ok(data)


@router.get("/{app_id}/versions")
def list_versions(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(app_service.list_versions(db, app_id))


@router.post("/{app_id}/versions")
@audit_log(module="应用管理", action="新建应用版本")
def create_version(
    app_id: int,
    body: AppVersionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(app_service.create_version(db, app_id, body))


@router.get("/{app_id}/versions/{version_id}")
def get_version(
    app_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(app_service.get_version(db, app_id, version_id))


@router.put("/{app_id}/versions/{version_id}")
@audit_log(module="应用管理", action="编辑应用版本")
def update_version(
    app_id: int,
    version_id: int,
    body: AppVersionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(app_service.update_version(db, app_id, version_id, body))


@router.delete("/{app_id}/versions/{version_id}")
@audit_log(module="应用管理", action="删除应用版本")
def delete_version(
    app_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    app_service.delete_version(db, app_id, version_id)
    return ok()


@public_router.get("/{app_id}/versions/{version_id}/package")
@no_audit
def download_package(
    app_id: int,
    version_id: int,
    db: Session = Depends(get_db),
):
    """设备侧按 bundleDownloadUrl 下载 HAP（白名单免登录）."""
    path, filename = app_service.get_package_path(db, app_id, version_id)
    return FileResponse(
        path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.post("/{app_id}/versions/{version_id}/package")
@audit_log(module="应用管理", action="上传应用安装包")
async def upload_package(
    app_id: int,
    version_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(await app_service.upload_package(db, app_id, version_id, file))


@public_router.get("/{app_id}/icon")
@no_audit
def download_icon(
    app_id: int,
    db: Session = Depends(get_db),
):
    """应用图标直链（列表/详情 img 用，免登录）."""
    path, filename = app_service.get_icon_path(db, app_id)
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


@router.post("/{app_id}/icon")
@audit_log(module="应用管理", action="上传应用图标")
async def upload_icon(
    app_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(await app_service.upload_icon(db, app_id, file))


@router.delete("/{app_id}/icon")
@audit_log(module="应用管理", action="清除应用图标")
def clear_icon(
    app_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.APP)),
):
    return ok(app_service.clear_icon(db, app_id))
