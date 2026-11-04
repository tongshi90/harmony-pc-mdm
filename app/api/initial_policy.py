from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.schemas.common import ok
from app.schemas.initial_policy import InitialPolicyCreate, InitialPolicyUpdate
from app.services import initial_policy_service

router = APIRouter(dependencies=[Depends(require_menu(MenuCode.MEMBER_GROUP))])


@router.get("/initial-policies")
def list_initial_policies(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER_GROUP)),
):
    return ok(initial_policy_service.list_policies(db, keyword, page, page_size))


@router.get("/initial-policies/{policy_id}")
def get_initial_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER_GROUP)),
):
    return ok(initial_policy_service.get_policy(db, policy_id))


@router.post("/initial-policies")
@audit_log(module="成员分组", action="新建初始策略模板")
def create_initial_policy(
    body: InitialPolicyCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER_GROUP)),
):
    return ok(initial_policy_service.create_policy(db, body))


@router.put("/initial-policies/{policy_id}")
@audit_log(module="成员分组", action="编辑初始策略模板")
def update_initial_policy(
    policy_id: int,
    body: InitialPolicyUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER_GROUP)),
):
    return ok(initial_policy_service.update_policy(db, policy_id, body))


@router.delete("/initial-policies/{policy_id}")
@audit_log(module="成员分组", action="删除初始策略模板")
def delete_initial_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.MEMBER_GROUP)),
):
    initial_policy_service.delete_policy(db, policy_id)
    return ok(True)
