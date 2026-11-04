"""初始策略模板：CRUD，策略项按 code + param_json + sort_order 落库."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.department import SysDepartment
from app.models.initial_policy import InitialPolicy, InitialPolicyItem
from app.utils.policy_summary import build_policy_item_summary, make_app_name_resolver
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now


def _fmt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _parse_param(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dumps_param(param: dict[str, Any] | None) -> str:
    return json.dumps(param or {}, ensure_ascii=False, separators=(",", ":"))


def _items_out(db: Session, policy_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(InitialPolicyItem)
        .filter(InitialPolicyItem.policy_id == policy_id)
        .order_by(InitialPolicyItem.sort_order.asc(), InitialPolicyItem.id.asc())
        .all()
    )
    return [
        {
            "id": str(r.id),
            "policy_code": r.policy_code,
            "param": _parse_param(r.param_json),
            "summary": (r.summary or "").strip()
            or build_policy_item_summary(r.policy_code, _parse_param(r.param_json)),
            "sort": int(r.sort_order or 0),
        }
        for r in rows
    ]


def _policy_out(db: Session, row: InitialPolicy, *, detail: bool = False) -> dict[str, Any]:
    items = _items_out(db, row.id)
    data = {
        "id": str(row.id),
        "name": row.name,
        "description": row.description or "",
        "item_count": len(items),
        "create_time": _fmt(row.create_time),
        "update_time": _fmt(row.update_time),
    }
    if detail:
        data["items"] = items
    return data


def _normalize_items(raw_items: list | None) -> list[tuple[str, dict[str, Any], int]]:
    """去重 policy_code（后者覆盖前者），并按 sort 排序后重新编号."""
    by_code: dict[str, tuple[str, dict[str, Any], int]] = {}
    for idx, it in enumerate(raw_items or []):
        code = (getattr(it, "policy_code", None) or "").strip()
        if not code:
            raise HTTPException(status_code=400, detail="策略项 policy_code 不能为空")
        # 兼容旧种子 Code
        if code == "PASSWORD_POLICY":
            code = "PSW_MANAGEMENT"
        param = getattr(it, "param", None) or {}
        if not isinstance(param, dict):
            raise HTTPException(status_code=400, detail=f"策略项 {code} 的 param 须为对象")
        sort = int(getattr(it, "sort", idx) or idx)
        by_code[code] = (code, param, sort)
    ordered = sorted(by_code.values(), key=lambda x: (x[2], x[0]))
    return [(code, param, i + 1) for i, (code, param, _) in enumerate(ordered)]


def _replace_items(
    db: Session, policy_id: int, raw_items: list | None
) -> None:
    db.query(InitialPolicyItem).filter(InitialPolicyItem.policy_id == policy_id).delete()
    ts = local_now()
    resolve = make_app_name_resolver(db)
    for code, param, sort in _normalize_items(raw_items):
        summary = build_policy_item_summary(code, param, resolve_app_name=resolve)
        db.add(
            InitialPolicyItem(
                id=snowflake_id(),
                policy_id=policy_id,
                policy_code=code,
                param_json=_dumps_param(param),
                summary=summary,
                sort_order=sort,
                create_time=ts,
                update_time=ts,
            )
        )


def list_policies(
    db: Session, keyword: str | None = None, page: int = 1, page_size: int = 50
) -> dict:
    q = db.query(InitialPolicy)
    kw = (keyword or "").strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(InitialPolicy.name.like(like))
    total = q.count()
    rows = (
        q.order_by(
            InitialPolicy.update_time.desc(),
            InitialPolicy.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_policy_out(db, r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_policy(db: Session, policy_id: int) -> dict:
    row = db.query(InitialPolicy).filter(InitialPolicy.id == policy_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="策略模板不存在")
    return _policy_out(db, row, detail=True)


def create_policy(db: Session, data) -> dict:
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写策略名称")
    ts = local_now()
    pk = snowflake_id()
    row = InitialPolicy(
        id=pk,
        name=name,
        description=(data.description or "").strip() or None,
        is_default=0,  # 列保留；不再使用「全局默认」能力
        create_time=ts,
        update_time=ts,
    )
    db.add(row)
    _replace_items(db, pk, data.items)
    db.commit()
    return get_policy(db, pk)


def update_policy(db: Session, policy_id: int, data) -> dict:
    row = db.query(InitialPolicy).filter(InitialPolicy.id == policy_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="策略模板不存在")
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="请填写策略名称")
        row.name = name
    if data.description is not None:
        row.description = data.description.strip() or None
    if data.items is not None:
        _replace_items(db, row.id, data.items)
    row.is_default = 0
    row.update_time = local_now()
    db.commit()
    return get_policy(db, policy_id)


def delete_policy(db: Session, policy_id: int) -> None:
    row = db.query(InitialPolicy).filter(InitialPolicy.id == policy_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="策略模板不存在")
    used = (
        db.query(SysDepartment)
        .filter(SysDepartment.initial_policy_id == policy_id)
        .count()
    )
    if used > 0:
        raise HTTPException(status_code=400, detail="该策略模板已被使用，无法删除")
    db.query(InitialPolicyItem).filter(InitialPolicyItem.policy_id == policy_id).delete()
    db.delete(row)
    db.commit()
