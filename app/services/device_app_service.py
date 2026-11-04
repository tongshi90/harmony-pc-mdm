"""设备侧应用市场：应用列表 / 详情."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.app_pkg import AppBase, AppVersion
from app.services.device_snapshot_service import _version_key


def _absolute_download_url(base_url: str | None, app_pk: int, version_id: int) -> str:
    path = f"/platform/app/{app_pk}/versions/{version_id}/package"
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return path
    return f"{base}{path}"


def _pick_latest_published(versions: list[AppVersion]) -> AppVersion | None:
    """已发布版本中取版本号最高者（优先 version_code，其次 version_name）."""
    published = [v for v in versions if int(v.status or 0) == 2]
    if not published:
        return None

    def sort_key(v: AppVersion) -> tuple:
        # 更高版本排前面；同版本用更大 id
        code_key = _version_key(v.version_code)
        name_key = _version_key(v.version_name)
        return (code_key, name_key, int(v.id or 0))

    return max(published, key=sort_key)


def _bundle_size_kb(file_size: int | None) -> int:
    """协议 bundleSize 单位为 KB."""
    return int(file_size or 0) // 1024


def list_market_apps(db: Session, *, public_base_url: str | None = None) -> dict:
    """上架应用列表：每条带最高已发布版本及下载地址."""
    apps = (
        db.query(AppBase)
        .filter(AppBase.status == 1)
        .order_by(AppBase.update_time.desc(), AppBase.id.desc())
        .all()
    )
    if not apps:
        return {"apps": []}

    app_ids = [int(a.id) for a in apps]
    versions = (
        db.query(AppVersion)
        .filter(AppVersion.app_id.in_(app_ids))
        .all()
    )
    by_app: dict[int, list[AppVersion]] = {}
    for v in versions:
        by_app.setdefault(int(v.app_id), []).append(v)

    items: list[dict] = []
    for app in apps:
        app_id = (app.app_id or "").strip()
        bundle = (app.bundle_name or "").strip()
        if not app_id or not bundle:
            continue
        latest = _pick_latest_published(by_app.get(int(app.id), []))
        if not latest:
            continue
        download = ""
        if latest.file_path:
            download = _absolute_download_url(
                public_base_url, int(app.id), int(latest.id)
            )
        items.append(
            {
                "appId": app_id,
                "appName": app.app_name or "",
                "appDesc": app.description or "",
                "bundleName": bundle,
                "version": (latest.version_name or "").strip(),
                "bundleDownloadUrl": download,
            }
        )
    return {"apps": items}


def get_market_app_info(
    db: Session, *, app_id: str, public_base_url: str | None = None
) -> dict:
    """应用详情：上架应用 + 最高已发布版本（含包大小；更新记录暂空）."""
    key = (app_id or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="请提供 appId")

    app = (
        db.query(AppBase)
        .filter(AppBase.app_id == key, AppBase.status == 1)
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在或已下架")

    bundle = (app.bundle_name or "").strip()
    if not bundle:
        raise HTTPException(status_code=404, detail="应用包名未配置")

    versions = (
        db.query(AppVersion)
        .filter(AppVersion.app_id == app.id)
        .all()
    )
    latest = _pick_latest_published(versions)
    if not latest or not latest.file_path:
        raise HTTPException(status_code=404, detail="暂无已发布的安装包")

    return {
        "appId": key,
        "appName": app.app_name or "",
        "appDesc": app.description or "",
        "bundleName": bundle,
        "version": (latest.version_name or "").strip(),
        "bundleDownloadUrl": _absolute_download_url(
            public_base_url, int(app.id), int(latest.id)
        ),
        "bundleSize": _bundle_size_kb(latest.file_size),
        # 版本更新记录字段尚未建模，暂返回空数组
        "changeLogs": [],
    }
