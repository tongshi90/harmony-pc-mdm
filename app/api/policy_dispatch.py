"""策略下发（管理台）."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.schemas.common import ok
from app.schemas.policy_dispatch import PolicyTaskCreate
from app.services import policy_dispatch_service

router = APIRouter(dependencies=[Depends(require_menu(MenuCode.POLICY_DISPATCH))])


@router.get("/targets/members")
def list_target_members(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.POLICY_DISPATCH)),
):
    """手动选人：仅返回已绑定设备的成员."""
    return ok(policy_dispatch_service.list_target_members(db, keyword, page, page_size))


@router.get("/tasks")
def list_policy_tasks(
    keyword: str | None = Query(None, description="任务名称 / 目标模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    op_type: str | None = Query(
        None,
        description="策略来源：dispatch | initial_bind | app_batch；省略或 all 表示全部",
    ),
    start_date: str | None = Query(None, description="创建日起 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="创建日止 YYYY-MM-DD（含当天）"),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.POLICY_DISPATCH)),
):
    return ok(
        policy_dispatch_service.list_tasks(
            db,
            keyword,
            page,
            page_size,
            op_type=op_type,
            start_date=start_date,
            end_date=end_date,
        )
    )


@router.get("/tasks/{task_id}")
def get_policy_task(
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.POLICY_DISPATCH)),
):
    return ok(policy_dispatch_service.get_task(db, task_id))


@router.get("/tasks/{task_id}/devices")
def list_policy_task_devices(
    task_id: int,
    keyword: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.POLICY_DISPATCH)),
):
    """兼容：返回任务目标设备清单（无执行状态）."""
    return ok(
        policy_dispatch_service.list_task_devices(
            db,
            task_id,
            keyword=keyword,
            status=status,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/device-sync")
def list_device_strategy_sync(
    keyword: str | None = Query(None),
    match: str | None = Query(None, description="matched | mismatched"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.POLICY_DISPATCH)),
):
    """终端策略对齐明细：预期/当前快照匹配或不匹配."""
    return ok(
        policy_dispatch_service.list_device_strategy_sync(
            db, keyword=keyword, match=match, page=page, page_size=page_size
        )
    )


@router.post("/tasks")
@audit_log(module="策略下发", action="创建并下发策略")
def create_policy_task(
    body: PolicyTaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_menu(MenuCode.POLICY_DISPATCH)),
):
    """校验并创建任务后立即返回；预期快照写入与 MQTT 通知在后台执行."""
    data = policy_dispatch_service.create_task(db, body, user)
    background_tasks.add_task(
        policy_dispatch_service.apply_dispatch_task_background, data["id"]
    )
    return ok(data)
