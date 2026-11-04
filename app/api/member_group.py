"""成员分组 CRUD（挂在 /platform/member-group）."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.schemas.common import ok
from app.schemas.department import DepartmentCreate, DepartmentUpdate
from app.services import department_service

router = APIRouter(dependencies=[Depends(require_menu(MenuCode.MEMBER_GROUP))])


@router.get("/groups")
def list_groups(
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER_GROUP)),
):
    return ok(department_service.list_departments(db, keyword))


@router.get("/groups/{group_id}")
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER_GROUP)),
):
    return ok(department_service.get_department(db, group_id))


@router.post("/groups")
@audit_log(module="成员分组", action="新建分组")
def create_group(
    body: DepartmentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER_GROUP)),
):
    return ok(department_service.create_department(db, body))


@router.put("/groups/{group_id}")
@audit_log(module="成员分组", action="编辑分组")
def update_group(
    group_id: int,
    body: DepartmentUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER_GROUP)),
):
    return ok(department_service.update_department(db, group_id, body))


@router.delete("/groups/{group_id}")
@audit_log(module="成员分组", action="删除分组")
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER_GROUP)),
):
    department_service.delete_department(db, group_id)
    return ok(True)
