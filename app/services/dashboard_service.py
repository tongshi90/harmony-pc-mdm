"""数据看板聚合统计（供 /platform/dashboard/overview）."""

from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.app_pkg import AppBase, AppVersion
from app.models.department import SysDepartment, SysMember
from app.models.device import Device, DeviceAppInstalled

APP_LIMIT = 12


def _device_stats(db: Session) -> dict:
    """在线/离线仅统计已绑定；挂失并入离线；未绑定单独一段。"""
    bound = (Device.bind_status == 1) & Device.member_id.isnot(None)
    unbound = (Device.bind_status == 0) | Device.member_id.is_(None)

    row = db.query(
        func.count(Device.id).label("total"),
        func.sum(case((bound & (Device.status == 1), 1), else_=0)).label("online"),
        func.sum(
            case((bound & (Device.status.in_((2, 3))), 1), else_=0)
        ).label("offline"),
        func.sum(case((unbound, 1), else_=0)).label("unbound"),
        func.sum(case((Device.is_compliant == 0, 1), else_=0)).label("noncompliant"),
    ).one()

    return {
        "total": int(row.total or 0),
        "online": int(row.online or 0),
        "offline": int(row.offline or 0),
        "unbound": int(row.unbound or 0),
        "noncompliant": int(row.noncompliant or 0),
    }


def _direct_member_counts(db: Session) -> dict[int, int]:
    rows = (
        db.query(SysMember.department_id, func.count(SysMember.id))
        .filter(SysMember.is_delete == 0)
        .group_by(SysMember.department_id)
        .all()
    )
    return {int(did): int(cnt) for did, cnt in rows if did is not None}


def _direct_device_counts(db: Session) -> dict[int, int]:
    rows = (
        db.query(SysMember.department_id, func.count(Device.id))
        .join(Device, Device.member_id == SysMember.id)
        .filter(SysMember.is_delete == 0)
        .group_by(SysMember.department_id)
        .all()
    )
    return {int(did): int(cnt) for did, cnt in rows if did is not None}


def _org_stats(db: Session) -> list[dict]:
    """返回组织树：每节点含本级及下级汇总的成员/终端数，供前端逐级下钻."""
    depts = db.query(SysDepartment).order_by(SysDepartment.id.asc()).all()
    if not depts:
        return []

    m_direct = _direct_member_counts(db)
    d_direct = _direct_device_counts(db)

    def rollup(node: SysDepartment) -> tuple[int, int]:
        prefix = (node.path or node.name) + "/"
        root_path = node.path or node.name
        members = 0
        devices = 0
        for d in depts:
            path = d.path or d.name
            if d.id == node.id or path == root_path or path.startswith(prefix):
                members += m_direct.get(d.id, 0)
                devices += d_direct.get(d.id, 0)
        return members, devices

    children_map: dict[int | None, list[SysDepartment]] = {}
    for d in depts:
        children_map.setdefault(d.parent_id, []).append(d)

    def build(node: SysDepartment) -> dict:
        members, devices = rollup(node)
        kids = children_map.get(node.id) or []
        child_nodes = [build(c) for c in kids]
        child_nodes.sort(
            key=lambda x: (-x["member_count"], -x["device_count"], x["name"])
        )
        return {
            "id": str(node.id),
            "name": node.name,
            "member_count": members,
            "device_count": devices,
            "unbound_member_count": max(0, members - devices),
            "has_children": bool(child_nodes),
            "children": child_nodes,
        }

    roots = children_map.get(None) or []
    # 无顶级时：把没有父节点在库中的节点当根（兜底）
    if not roots:
        known = {d.id for d in depts}
        roots = [d for d in depts if d.parent_id is None or d.parent_id not in known]

    items = [build(r) for r in roots]
    items.sort(key=lambda x: (-x["member_count"], -x["device_count"], x["name"]))
    return items


def _app_stats(db: Session) -> list[dict]:
    """各应用：已安装 / 未安装（设备总数 − 已装），并附各版本安装台数."""
    device_total = int(db.query(func.count(Device.id)).scalar() or 0)

    install_rows = (
        db.query(
            DeviceAppInstalled.app_id,
            func.count(DeviceAppInstalled.id).label("install_count"),
        )
        .group_by(DeviceAppInstalled.app_id)
        .all()
    )
    install_map = {int(aid): int(cnt) for aid, cnt in install_rows}

    # 按版本统计安装量
    ver_install_rows = (
        db.query(
            DeviceAppInstalled.app_id,
            DeviceAppInstalled.app_version_id,
            func.count(DeviceAppInstalled.id).label("cnt"),
        )
        .group_by(DeviceAppInstalled.app_id, DeviceAppInstalled.app_version_id)
        .all()
    )
    ver_install_map: dict[int, dict[int, int]] = {}
    for aid, vid, cnt in ver_install_rows:
        ver_install_map.setdefault(int(aid), {})[int(vid)] = int(cnt)

    all_versions = (
        db.query(AppVersion)
        .order_by(AppVersion.app_id.asc(), AppVersion.id.desc())
        .all()
    )
    versions_by_app: dict[int, list[AppVersion]] = {}
    for v in all_versions:
        versions_by_app.setdefault(int(v.app_id), []).append(v)

    apps = db.query(AppBase).order_by(AppBase.id.asc()).all()
    items: list[dict] = []
    for app in apps:
        aid = int(app.id)
        vers = versions_by_app.get(aid) or []
        install_count = install_map.get(aid, 0)
        if install_count <= 0 and not vers:
            continue
        not_installed = max(device_total - install_count, 0)
        v_installs = ver_install_map.get(aid) or {}
        version_items: list[dict] = []
        for v in vers:
            vid = int(v.id)
            version_items.append(
                {
                    "id": str(vid),
                    "version_name": v.version_name or "",
                    "version_code": v.version_code or "",
                    "install_count": v_installs.get(vid, 0),
                }
            )
        # 安装量优先，同量按版本号名
        version_items.sort(
            key=lambda x: (-x["install_count"], x["version_name"], x["version_code"])
        )
        items.append(
            {
                "id": str(aid),
                "app_name": app.app_name,
                "device_total": device_total,
                "install_count": install_count,
                "not_installed_count": not_installed,
                "version_count": len(version_items),
                "versions": version_items,
            }
        )

    items.sort(
        key=lambda x: (-x["install_count"], -x["version_count"], x["app_name"])
    )
    return items[:APP_LIMIT]


def get_overview(db: Session) -> dict:
    return {
        "devices": _device_stats(db),
        "org": _org_stats(db),
        "apps": _app_stats(db),
    }
