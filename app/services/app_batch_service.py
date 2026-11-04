"""应用批量安装 / 卸载：写策略变更日志 + 按规则合并 APP_MANAGEMENT 预期快照."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.enums.policy_change_op import APP_BATCH, resolve_policy_timing
from app.models.app_pkg import AppBase, AppVersion
from app.models.department import SysDepartment
from app.models.policy_task import PolicyDeviceTask, PolicyTask, PolicyTaskItem
from app.models.user import User
from app.mqtt import publish_mqtt_many
from app.services import device_snapshot_service
from app.services.device_online_sync_service import sync_device_online_status
from app.services.policy_dispatch_service import (
    MQTT_STRATEGY_PULL_PAYLOAD,
    _parse_param,
    _resolve_targets,
    get_task,
)
from app.utils.policy_summary import (
    aggregate_policy_summaries,
    build_policy_item_summary,
    make_app_name_resolver,
)
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

logger = logging.getLogger("mdm.app.batch")

POLICY_CODE = "APP_MANAGEMENT"
Action = Literal["install", "uninstall"]


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _absolute_download_url(base_url: str | None, app_pk: int, version_id: int) -> str:
    path = f"/platform/app/{app_pk}/versions/{version_id}/package"
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return path
    return f"{base}{path}"


def _load_app(db: Session, app_id: int) -> AppBase:
    app = db.query(AppBase).filter(AppBase.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    return app


def _load_published_version(db: Session, app_id: int, version_id: int) -> AppVersion:
    ver = (
        db.query(AppVersion)
        .filter(AppVersion.id == version_id, AppVersion.app_id == app_id)
        .first()
    )
    if not ver:
        raise HTTPException(status_code=404, detail="应用版本不存在")
    if int(ver.status or 0) != 2:
        raise HTTPException(status_code=400, detail="仅可选择已发布版本")
    if not ver.file_path:
        raise HTTPException(status_code=400, detail="该版本尚未上传安装包")
    return ver


def _resolve_group_targets(
    db: Session, *, group_ids: list[str], all_groups: bool
) -> tuple[list, str, list[str]]:
    if all_groups:
        # 取顶级分组即可（解析时会递归含子组），覆盖全组织
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
        devices, group_desc, group_id_strs = _resolve_targets(
            db, target_type="group", group_ids=ids, member_ids=[]
        )
        # 与分组下发一致：展示人数（取 group_desc 末尾「N 人」）
        people = group_desc.rsplit("·", 1)[-1].strip() if "·" in group_desc else ""
        desc = f"全部分组（含子组）· {people}" if people else "全部分组（含子组）"
        return devices, desc, group_id_strs
    if not group_ids:
        raise HTTPException(status_code=400, detail="请选择成员分组")
    return _resolve_targets(
        db, target_type="group", group_ids=list(group_ids), member_ids=[]
    )


def _build_install_entry(
    app: AppBase, ver: AppVersion, *, public_base_url: str | None
) -> dict[str, Any]:
    app_id = (app.app_id or "").strip()
    bundle = (app.bundle_name or "").strip()
    if not app_id or not bundle:
        raise HTTPException(status_code=400, detail="应用缺少 App ID 或 Bundle Name")
    return {
        "appId": app_id,
        "bundleName": bundle,
        "version": (ver.version_name or "").strip(),
        "bundleDownloadUrl": _absolute_download_url(
            public_base_url, int(app.id), int(ver.id)
        ),
    }


def _merge_task_ext(db: Session, task_id: int, patch: dict[str, Any]) -> None:
    row = db.query(PolicyTask).filter(PolicyTask.id == task_id).first()
    if not row:
        return
    cur = _parse_param(row.ext_json) if row.ext_json else {}
    if not isinstance(cur, dict):
        cur = {}
    cur.update(patch or {})
    row.ext_json = _dumps(cur)
    row.update_time = local_now()


def _run_batch(
    db: Session,
    *,
    app_id: int,
    action: Action,
    group_ids: list[str],
    all_groups: bool,
    version_id: str | None,
    public_base_url: str | None,
    creator: User | None,
) -> dict[str, Any]:
    """同步：校验并创建任务 + 目标设备明细；合并快照与 MQTT 由后台执行."""
    app = _load_app(db, app_id)
    app_name = (app.app_name or app.app_code or str(app.id)).strip()

    install_entry: dict[str, Any] | None = None
    ver: AppVersion | None = None
    if action == "install":
        if not version_id:
            raise HTTPException(status_code=400, detail="请选择版本")
        try:
            vid = int(version_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="版本 ID 无效") from exc
        ver = _load_published_version(db, app_id, vid)
        install_entry = _build_install_entry(app, ver, public_base_url=public_base_url)
        task_param: dict[str, Any] = {
            "currentApps": [install_entry],
            "uninstallApps": [],
        }
        task_name = f"{app_name} 批量安装"
    else:
        bundle = (app.bundle_name or "").strip()
        if not bundle:
            raise HTTPException(status_code=400, detail="应用缺少 Bundle Name，无法卸载")
        task_param = {
            "currentApps": [],
            "uninstallApps": [bundle],
        }
        task_name = f"{app_name} 批量卸载"

    devices, target_desc, group_id_strs = _resolve_group_targets(
        db, group_ids=group_ids, all_groups=all_groups
    )
    if not devices:
        raise HTTPException(status_code=400, detail="所选范围内无可用设备")

    ts = local_now()
    task_id = snowflake_id()
    creator_id = creator.id if creator else None
    creator_name = ""
    if creator:
        creator_name = (creator.name or creator.username or "").strip()

    resolve = make_app_name_resolver(db)
    item_summary = build_policy_item_summary(
        POLICY_CODE, task_param, resolve_app_name=resolve
    )

    ext: dict[str, Any] = {
        "action": action,
        "app_id": str(app.id),
        "app_name": app_name,
        "bundle_name": (app.bundle_name or "").strip(),
        "all_groups": bool(all_groups),
        "apply_status": "pending",
    }
    if ver is not None:
        ext["version_id"] = str(ver.id)
        ext["version_name"] = ver.version_name
        ext["version_code"] = ver.version_code
    if install_entry is not None:
        ext["install_entry"] = install_entry

    # 应用安装/卸载：固定普通策略，最多等待 24 小时
    level, wait_hours, deadline_at = resolve_policy_timing(
        op_type=APP_BATCH, now=ts
    )

    task = PolicyTask(
        id=task_id,
        op_type=APP_BATCH,
        name=task_name,
        policy_level=level,
        wait_hours=wait_hours,
        deadline_at=deadline_at,
        target_json=_dumps(group_id_strs),
        target_desc=target_desc,
        source_id=int(app.id),
        ext_json=_dumps(ext),
        creator_id=creator_id,
        creator_name=creator_name or None,
        target_count=len(devices),
        policy_summary=aggregate_policy_summaries([item_summary]),
        create_time=ts,
        update_time=ts,
    )
    db.add(task)
    db.add(
        PolicyTaskItem(
            id=snowflake_id(),
            task_id=task_id,
            policy_code=POLICY_CODE,
            param_json=_dumps(task_param),
            summary=item_summary,
            sort_order=1,
            create_time=ts,
            update_time=ts,
        )
    )

    dept_ids = {
        int(m.department_id)
        for _d, m in devices
        if m is not None and m.department_id is not None
    }
    dept_map: dict[int, SysDepartment] = {}
    if dept_ids:
        for d in db.query(SysDepartment).filter(SysDepartment.id.in_(dept_ids)).all():
            dept_map[int(d.id)] = d

    for device, member in devices:
        dept = None
        if member is not None and member.department_id is not None:
            dept = dept_map.get(int(member.department_id))
        db.add(
            PolicyDeviceTask(
                id=snowflake_id(),
                task_id=task_id,
                device_id=device.id,
                device_sn=device.sn,
                member_id=member.id if member else device.member_id,
                member_name=(member.name if member else None),
                employee_id=(member.employee_id if member else None),
                department_id=(member.department_id if member else None),
                department_path=(
                    (dept.path if dept else None) or (dept.name if dept else None)
                ),
                create_time=ts,
                update_time=ts,
            )
        )

    db.commit()
    out = get_task(db, task_id)
    out["accepted"] = True
    out["message"] = (
        f"{'批量安装' if action == 'install' else '批量卸载'}任务已创建，"
        "正在后台下发，请稍后查看执行结果"
    )
    out["batch_stats"] = {"apply_status": "pending", "targets": len(devices)}
    return out


def apply_app_batch_task_background(task_id: int | str) -> None:
    """后台：按设备合并 APP_MANAGEMENT 预期，整批 commit 后并行 MQTT."""
    try:
        tid = int(task_id)
    except (TypeError, ValueError):
        logger.error("应用批量后台任务无效 task_id=%s", task_id)
        return

    db = SessionLocal()
    try:
        task = db.query(PolicyTask).filter(PolicyTask.id == tid).first()
        if not task:
            logger.error("应用批量后台任务不存在 task_id=%s", tid)
            return

        ext = _parse_param(task.ext_json) if task.ext_json else {}
        if not isinstance(ext, dict):
            ext = {}
        action = str(ext.get("action") or "").strip()
        if action not in ("install", "uninstall"):
            logger.error("应用批量任务缺少 action task_id=%s", tid)
            _merge_task_ext(db, tid, {"apply_status": "failed"})
            db.commit()
            return

        _merge_task_ext(db, tid, {"apply_status": "applying"})
        db.commit()

        install_entry = ext.get("install_entry")
        if not isinstance(install_entry, dict):
            install_entry = None
        bundle_name = str(ext.get("bundle_name") or "").strip()

        device_rows = (
            db.query(PolicyDeviceTask)
            .filter(PolicyDeviceTask.task_id == tid)
            .order_by(PolicyDeviceTask.id.asc())
            .all()
        )

        stats = {"skipped": 0, "updated": 0, "added": 0, "changed_devices": 0}
        snapshot_failed = 0
        notify_sns: list[str] = []

        for drow in device_rows:
            sn = (drow.device_sn or "").strip()
            if not sn:
                snapshot_failed += 1
                continue
            try:
                with db.begin_nested():
                    existing = device_snapshot_service.get_expected_param(
                        db, sn, POLICY_CODE
                    )
                    if action == "install":
                        if not install_entry:
                            raise RuntimeError("缺少 install_entry")
                        merged, op = device_snapshot_service.merge_app_management_install(
                            existing,
                            app_entry=install_entry,
                        )
                    else:
                        merged, op = device_snapshot_service.merge_app_management_uninstall(
                            existing,
                            bundle_name=bundle_name,
                        )
                    if op != "skipped":
                        device_snapshot_service.upsert_expected(
                            db,
                            device_sn=sn,
                            policy_code=POLICY_CODE,
                            param=merged,
                            commit=False,
                        )
                        device_snapshot_service.refresh_device_compliance(
                            db, sn, commit=False
                        )
                stats[op] = stats.get(op, 0) + 1
                if op != "skipped":
                    stats["changed_devices"] += 1
                    notify_sns.append(sn)
            except Exception:
                snapshot_failed += 1
                logger.exception(
                    "应用批量写预期快照失败 sn=%s task=%s action=%s", sn, tid, action
                )

        db.commit()

        sync = sync_device_online_status()
        if sync.ok:
            online_set: set[str] | None = {
                str(x).strip() for x in sync.online_sns if str(x).strip()
            }
        else:
            online_set = None
            logger.warning(
                "应用批量后台在线同步失败，降级全量尝试通知: %s", sync.message
            )

        skipped_offline = 0
        mqtt_targets: list[str] = []
        for sn in notify_sns:
            if online_set is not None and sn not in online_set:
                skipped_offline += 1
                continue
            mqtt_targets.append(sn)

        mqtt_stats = publish_mqtt_many(
            mqtt_targets, message=MQTT_STRATEGY_PULL_PAYLOAD, qos=1
        )
        result = {
            "apply_status": "done",
            **stats,
            "snapshot_failed": snapshot_failed,
            "notified": int(mqtt_stats.get("notified") or 0),
            "notify_failed": int(mqtt_stats.get("failed") or 0),
            "skipped_offline": skipped_offline,
        }
        _merge_task_ext(db, tid, result)
        db.commit()
        logger.info(
            "应用批量后台完成 task=%s action=%s 目标=%s 变更=%s 通知=%s 离线跳过=%s 失败=%s",
            tid,
            action,
            len(device_rows),
            stats["changed_devices"],
            result["notified"],
            skipped_offline,
            result["notify_failed"],
        )
    except Exception:
        logger.exception("应用批量后台任务异常 task_id=%s", tid)
        try:
            db.rollback()
            _merge_task_ext(db, tid, {"apply_status": "failed"})
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    finally:
        db.close()


def batch_install(
    db: Session,
    app_id: int,
    *,
    group_ids: list[str],
    all_groups: bool,
    version_id: str,
    public_base_url: str | None,
    creator: User | None,
) -> dict[str, Any]:
    return _run_batch(
        db,
        app_id=app_id,
        action="install",
        group_ids=group_ids,
        all_groups=all_groups,
        version_id=version_id,
        public_base_url=public_base_url,
        creator=creator,
    )


def batch_uninstall(
    db: Session,
    app_id: int,
    *,
    group_ids: list[str],
    all_groups: bool,
    creator: User | None,
) -> dict[str, Any]:
    return _run_batch(
        db,
        app_id=app_id,
        action="uninstall",
        group_ids=group_ids,
        all_groups=all_groups,
        version_id=None,
        public_base_url=None,
        creator=creator,
    )
