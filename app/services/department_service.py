"""成员分组（部门）CRUD；成员数 / 关联终端按本级+全部子孙汇总."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.department import SysDepartment, SysMember
from app.models.device import Device
from app.models.initial_policy import InitialPolicy
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now


def _fmt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _get_dept(db: Session, dept_id: int) -> SysDepartment:
    row = db.query(SysDepartment).filter(SysDepartment.id == dept_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="分组不存在")
    return row


def _policy_map(db: Session) -> dict[int, InitialPolicy]:
    rows = db.query(InitialPolicy).all()
    return {r.id: r for r in rows}


def _direct_member_counts(db: Session) -> dict[int, int]:
    """仅本级成员数（不含下级）."""
    rows = (
        db.query(SysMember.department_id, func.count(SysMember.id))
        .filter(SysMember.is_delete == 0)
        .group_by(SysMember.department_id)
        .all()
    )
    return {int(did): int(cnt) for did, cnt in rows if did is not None}


def _direct_device_counts(db: Session) -> dict[int, int]:
    """仅本级已绑定设备数（按人员所属部门；不含下级）."""
    rows = (
        db.query(SysMember.department_id, func.count(Device.id))
        .join(Device, Device.member_id == SysMember.id)
        .filter(SysMember.is_delete == 0)
        .group_by(SysMember.department_id)
        .all()
    )
    return {int(did): int(cnt) for did, cnt in rows if did is not None}


def _rollup_counts(
    depts: list[SysDepartment], direct: dict[int, int]
) -> dict[int, int]:
    """本级 + 全部子孙合计（按 path 前缀匹配下级）."""
    out: dict[int, int] = {}
    for node in depts:
        root_path = node.path or node.name
        prefix = root_path + "/"
        total = 0
        for d in depts:
            path = d.path or d.name
            if d.id == node.id or path == root_path or path.startswith(prefix):
                total += direct.get(d.id, 0)
        out[int(node.id)] = total
    return out


def _member_counts(db: Session, depts: list[SysDepartment] | None = None) -> dict[int, int]:
    """分组成员数：含本级及所有下级."""
    all_depts = depts if depts is not None else db.query(SysDepartment).all()
    return _rollup_counts(all_depts, _direct_member_counts(db))


def _device_counts(db: Session, depts: list[SysDepartment] | None = None) -> dict[int, int]:
    """分组关联终端数：含本级及所有下级（经人员绑定统计）."""
    all_depts = depts if depts is not None else db.query(SysDepartment).all()
    return _rollup_counts(all_depts, _direct_device_counts(db))


def _depth_of(path: str) -> int:
    if not path:
        return 0
    return max(0, path.count("/"))


def _build_path(db: Session, name: str, parent_id: int | None) -> str:
    name = name.strip()
    if not parent_id:
        return name
    parent = _get_dept(db, parent_id)
    return f"{parent.path}/{name}"


def _descendant_ids(db: Session, dept_id: int) -> set[int]:
    """含自身的子孙 id（按 path 前缀）。"""
    row = _get_dept(db, dept_id)
    prefix = row.path + "/"
    ids = {row.id}
    for d in db.query(SysDepartment).all():
        if d.id == row.id:
            continue
        if d.path == row.path or d.path.startswith(prefix):
            ids.add(d.id)
    return ids


def _validate_parent(db: Session, parent_id: int | None, self_id: int | None = None) -> None:
    if parent_id is None:
        return
    parent = _get_dept(db, parent_id)
    if self_id is not None:
        if parent_id == self_id:
            raise HTTPException(status_code=400, detail="上级分组不能是自身")
        if parent.id in _descendant_ids(db, self_id):
            raise HTTPException(status_code=400, detail="上级分组不能是当前分组的下级")


def _validate_policy(db: Session, policy_id: int | None) -> None:
    if policy_id is None:
        return
    exists = db.query(InitialPolicy).filter(InitialPolicy.id == policy_id).first()
    if not exists:
        raise HTTPException(status_code=400, detail="初始策略模板不存在")


def _dept_out(
    row: SysDepartment,
    *,
    policies: dict[int, InitialPolicy],
    member_counts: dict[int, int],
    device_counts: dict[int, int],
) -> dict[str, Any]:
    policy = policies.get(row.initial_policy_id) if row.initial_policy_id else None
    return {
        "id": str(row.id),
        "parent_id": str(row.parent_id) if row.parent_id else None,
        "name": row.name,
        "path": row.path or row.name,
        "depth": _depth_of(row.path or row.name),
        "description": row.description or "",
        "initial_policy_id": str(row.initial_policy_id) if row.initial_policy_id else None,
        "initial_policy_name": policy.name if policy else None,
        "member_count": member_counts.get(row.id, 0),
        "device_count": device_counts.get(row.id, 0),
        "status": row.status,
        "create_time": _fmt(row.create_time),
        "update_time": _fmt(row.update_time),
    }


def list_departments(db: Session, keyword: str | None = None) -> dict:
    all_depts = db.query(SysDepartment).all()
    q = db.query(SysDepartment)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            (SysDepartment.name.like(like)) | (SysDepartment.path.like(like))
        )
    rows = q.order_by(SysDepartment.path.asc(), SysDepartment.id.asc()).all()
    policies = _policy_map(db)
    # 汇总基于全部分组树，避免关键词过滤后漏计未命中的子孙
    mcounts = _member_counts(db, all_depts)
    dcounts = _device_counts(db, all_depts)
    items = [
        _dept_out(r, policies=policies, member_counts=mcounts, device_counts=dcounts)
        for r in rows
    ]
    return {"items": items, "total": len(items)}


def get_department(db: Session, dept_id: int) -> dict:
    row = _get_dept(db, dept_id)
    all_depts = db.query(SysDepartment).all()
    return _dept_out(
        row,
        policies=_policy_map(db),
        member_counts=_member_counts(db, all_depts),
        device_counts=_device_counts(db, all_depts),
    )


def _assert_name_unique(
    db: Session, name: str, *, exclude_id: int | None = None
) -> None:
    """分组名全局唯一（导入按名称匹配；不允许跨层级重名）."""
    q = db.query(SysDepartment).filter(SysDepartment.name == name)
    if exclude_id is not None:
        q = q.filter(SysDepartment.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=400, detail="分组名称已存在，不允许重复")


def create_department(db: Session, data) -> dict:
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写分组名称")
    parent_id = data.parent_id
    _validate_parent(db, parent_id)
    _validate_policy(db, data.initial_policy_id)
    path = _build_path(db, name, parent_id)
    _assert_name_unique(db, name)
    ts = local_now()
    pk = snowflake_id()
    row = SysDepartment(
        id=pk,
        parent_id=parent_id,
        name=name,
        path=path,
        description=(data.description or "").strip() or None,
        initial_policy_id=data.initial_policy_id,
        status=int(data.status if data.status is not None else 1),
        create_time=ts,
        update_time=ts,
    )
    db.add(row)
    db.commit()
    return get_department(db, pk)


def _rebuild_subtree_paths(db: Session, root: SysDepartment) -> None:
    """父节点 path/name 变更后，重算所有子孙 path."""
    children = (
        db.query(SysDepartment)
        .filter(SysDepartment.parent_id == root.id)
        .order_by(SysDepartment.id.asc())
        .all()
    )
    for child in children:
        child.path = f"{root.path}/{child.name}"
        child.update_time = local_now()
        _rebuild_subtree_paths(db, child)


def update_department(db: Session, dept_id: int, data) -> dict:
    """编辑不允许修改上级分组（忽略请求中的 parent_id，沿用库中现值）."""
    row = _get_dept(db, dept_id)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写分组名称")
    parent_id = row.parent_id
    _validate_policy(db, data.initial_policy_id)

    _assert_name_unique(db, name, exclude_id=dept_id)

    old_path = row.path
    row.name = name
    # parent_id 不变
    row.path = _build_path(db, name, parent_id)
    row.description = (data.description or "").strip() or None
    row.initial_policy_id = data.initial_policy_id
    row.status = int(data.status if data.status is not None else 1)
    row.update_time = local_now()

    if row.path != old_path:
        _rebuild_subtree_paths(db, row)

    db.commit()
    return get_department(db, dept_id)


def delete_department(db: Session, dept_id: int) -> None:
    """删除本部门及全部子部门；任一节点下仍有未删除成员则整单拒绝."""
    row = _get_dept(db, dept_id)
    subtree_ids = _descendant_ids(db, dept_id)
    member = (
        db.query(SysMember)
        .filter(
            SysMember.department_id.in_(list(subtree_ids)),
            SysMember.is_delete == 0,
        )
        .first()
    )
    if member:
        raise HTTPException(
            status_code=400,
            detail="分组或其下级分组下仍有成员，无法删除",
        )
    # 先删子孙再删自身（按 path 深度降序，避免依赖顺序时的歧义）
    rows = (
        db.query(SysDepartment)
        .filter(SysDepartment.id.in_(list(subtree_ids)))
        .all()
    )
    rows.sort(key=lambda r: (_depth_of(r.path or r.name), r.id), reverse=True)
    for r in rows:
        db.delete(r)
    db.commit()
