"""人员管理：姓名 / 工号 / 账号 / 密码 / 分组；工号与账号唯一."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import exists

from app.models.department import SysDepartment, SysMember
from app.models.device import Device
from app.utils.crypto import decrypt_password
from app.utils.security import hash_password
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now


def _fmt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _parse_id(raw) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="无效的分组 ID") from exc


def _get_member(db: Session, member_id: int) -> SysMember:
    row = (
        db.query(SysMember)
        .filter(SysMember.id == member_id, SysMember.is_delete == 0)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="成员不存在")
    return row


def _ensure_department(db: Session, department_id: int) -> SysDepartment:
    row = db.query(SysDepartment).filter(SysDepartment.id == department_id).first()
    if not row:
        raise HTTPException(status_code=400, detail="所属分组不存在")
    return row


def _assert_unique(
    db: Session,
    *,
    employee_id: str | None = None,
    account: str | None = None,
    exclude_id: int | None = None,
) -> None:
    if employee_id is not None:
        q = db.query(SysMember).filter(
            SysMember.employee_id == employee_id,
            SysMember.is_delete == 0,
        )
        if exclude_id is not None:
            q = q.filter(SysMember.id != exclude_id)
        if q.first():
            raise HTTPException(status_code=400, detail="工号已存在，不允许重复")
    if account is not None:
        q = db.query(SysMember).filter(
            SysMember.account == account,
            SysMember.is_delete == 0,
        )
        if exclude_id is not None:
            q = q.filter(SysMember.id != exclude_id)
        if q.first():
            raise HTTPException(status_code=400, detail="账号已存在，不允许重复")


def _dept_map(db: Session, dept_ids: set[int]) -> dict[int, SysDepartment]:
    if not dept_ids:
        return {}
    rows = db.query(SysDepartment).filter(SysDepartment.id.in_(list(dept_ids))).all()
    return {r.id: r for r in rows}


def _device_bindings(db: Session, member_ids: set[int]) -> dict[int, str]:
    """一人一设备：返回 member_id → device_sn（若有多条仅取一条）."""
    if not member_ids:
        return {}
    rows = (
        db.query(Device.member_id, Device.sn)
        .filter(Device.member_id.in_(list(member_ids)))
        .order_by(Device.id.asc())
        .all()
    )
    out: dict[int, str] = {}
    for mid, sn in rows:
        if mid is None:
            continue
        key = int(mid)
        if key not in out:
            out[key] = sn or ""
    return out


def _member_out(
    row: SysMember,
    dept: SysDepartment | None,
    *,
    device_sn: str | None = None,
    with_bind: bool = False,
) -> dict[str, Any]:
    data = {
        "id": str(row.id),
        "name": row.name,
        "employee_id": row.employee_id,
        "account": row.account,
        "department_id": str(row.department_id),
        "department_path": (dept.path if dept else "") or (dept.name if dept else ""),
        "department_name": dept.name if dept else "",
        "status": row.status,
        "create_time": _fmt(row.create_time),
        "update_time": _fmt(row.update_time),
    }
    if with_bind:
        sn = (device_sn or "").strip()
        data["bound"] = bool(sn)
        data["device_sn"] = sn or None
    return data


def list_members(
    db: Session,
    keyword: str | None = None,
    department_id: int | None = None,
    bind: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    q = db.query(SysMember).filter(SysMember.is_delete == 0)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(
            (SysMember.name.like(like))
            | (SysMember.employee_id.like(like))
            | (SysMember.account.like(like))
        )
    if department_id is not None:
        q = q.filter(SysMember.department_id == department_id)
    # 绑定筛选：有设备 member_id 指向该成员即为已绑定（与列表 bound 展示一致）
    bd = (bind or "").strip().lower()
    has_device = exists().where(Device.member_id == SysMember.id)
    if bd == "bound":
        q = q.filter(has_device)
    elif bd == "unbound":
        q = q.filter(~has_device)
    total = q.count()
    rows = (
        q.order_by(SysMember.create_time.asc(), SysMember.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    depts = _dept_map(db, {r.department_id for r in rows})
    bindings = _device_bindings(db, {r.id for r in rows})
    return {
        "items": [
            _member_out(
                r,
                depts.get(r.department_id),
                device_sn=bindings.get(r.id),
                with_bind=True,
            )
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_member(db: Session, member_id: int) -> dict:
    row = _get_member(db, member_id)
    dept = _ensure_department(db, row.department_id)
    bindings = _device_bindings(db, {row.id})
    return _member_out(
        row,
        dept,
        device_sn=bindings.get(row.id),
        with_bind=True,
    )


def create_member(db: Session, data) -> dict:
    name = data.name.strip()
    employee_id = data.employee_id.strip()
    account = data.account.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写姓名")
    if not employee_id:
        raise HTTPException(status_code=400, detail="请填写工号")
    if not account:
        raise HTTPException(status_code=400, detail="请填写账号")

    department_id = _parse_id(data.department_id)
    dept = _ensure_department(db, department_id)
    _assert_unique(db, employee_id=employee_id, account=account)

    try:
        password = decrypt_password(data.password)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="密码解密失败") from exc
    if not password:
        raise HTTPException(status_code=400, detail="请填写密码")

    ts = local_now()
    pk = snowflake_id()
    row = SysMember(
        id=pk,
        department_id=department_id,
        name=name,
        employee_id=employee_id,
        account=account,
        password=hash_password(password),
        status=int(data.status if data.status is not None else 1),
        is_delete=0,
        create_time=ts,
        update_time=ts,
    )
    db.add(row)
    db.commit()
    return _member_out(row, dept)


def update_member(db: Session, member_id: int, data) -> dict:
    """编辑不可改账号、密码."""
    row = _get_member(db, member_id)
    name = data.name.strip()
    employee_id = data.employee_id.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写姓名")
    if not employee_id:
        raise HTTPException(status_code=400, detail="请填写工号")

    department_id = _parse_id(data.department_id)
    dept = _ensure_department(db, department_id)
    _assert_unique(db, employee_id=employee_id, exclude_id=row.id)

    row.name = name
    row.employee_id = employee_id
    row.department_id = department_id
    row.status = int(data.status if data.status is not None else 1)
    row.update_time = local_now()
    db.commit()
    return _member_out(row, dept)


def delete_member(db: Session, member_id: int) -> None:
    row = _get_member(db, member_id)
    bound = (
        db.query(Device)
        .filter(Device.member_id == member_id)
        .first()
    )
    if bound:
        raise HTTPException(status_code=400, detail="已绑定设备的成员无法删除")
    row.is_delete = 1
    row.update_time = local_now()
    db.commit()
