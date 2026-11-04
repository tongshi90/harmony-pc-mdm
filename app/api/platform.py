from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.schemas.common import ok
from app.schemas.log_config import LogConfigUpdate
from app.schemas.mqtt import MqttConfigUpdate
from app.schemas.role import RoleCreate, RoleStatusUpdate, RoleUpdate
from app.schemas.user import AdminCreate, AdminResetPassword, AdminStatusUpdate, AdminUpdate
from app.services import log_config_service, mqtt_service, op_log_service, role_service, user_service
from app.services.permission_service import list_fixed_menus

router = APIRouter(
    dependencies=[Depends(require_menu(MenuCode.PLATFORM))],
)


# ---------- 固定菜单（角色配置页使用，前端不再单独展示清单） ----------
@router.get("/menus")
def menus(_: User = Depends(require_menu(MenuCode.PLATFORM))):
    return ok(list_fixed_menus())


# ---------- 系统配置：MQTT ----------
@router.get("/mqtt")
def get_mqtt(db: Session = Depends(get_db), _: User = Depends(require_menu(MenuCode.PLATFORM))):
    return ok(mqtt_service.get_config(db))


@router.post("/mqtt/test")
@audit_log(module="平台基础管理", action="探测 MQTT 连接")
def test_mqtt(
    body: MqttConfigUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    """用表单参数尝试连接 Broker；成功才允许前端点保存."""
    return ok(mqtt_service.test_config(db, body))


@router.put("/mqtt")
@audit_log(module="平台基础管理", action="保存 MQTT 配置")
def update_mqtt(
    body: MqttConfigUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(mqtt_service.update_config(db, body))


# ---------- 系统配置：操作日志保留 ----------
@router.get("/log-config")
def get_log_config(
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(log_config_service.get_config(db))


@router.put("/log-config")
@audit_log(module="平台基础管理", action="保存日志保留配置")
def update_log_config(
    body: LogConfigUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(log_config_service.update_config(db, body))


# ---------- 操作日志 ----------
@router.get("/op-logs")
def list_op_logs(
    keyword: str | None = Query(None),
    success: int | None = Query(None, ge=0, le=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(
        op_log_service.list_logs(
            db, current, keyword=keyword, success=success, page=page, page_size=page_size
        )
    )


@router.get("/op-logs/export")
@audit_log(module="平台基础管理", action="导出操作日志")
def export_op_logs(
    keyword: str | None = Query(None),
    success: int | None = Query(None, ge=0, le=1),
    db: Session = Depends(get_db),
    current: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    data = op_log_service.export_logs_csv(db, current, keyword=keyword, success=success)
    filename = "op-logs.csv"
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/op-logs/{log_id}")
def get_op_log(
    log_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(op_log_service.get_log(db, current, log_id))


# ---------- 管理员 ----------
@router.get("/admins")
def list_admins(
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(user_service.list_admins(db, keyword, page, page_size))


@router.get("/admins/{user_id}")
def get_admin(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(user_service.get_admin(db, user_id))


@router.post("/admins")
@audit_log(module="平台基础管理", action="新建管理员")
def create_admin(
    body: AdminCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(user_service.create_admin(db, body))


@router.put("/admins/{user_id}")
@audit_log(module="平台基础管理", action="编辑管理员")
def update_admin(
    user_id: int,
    body: AdminUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(user_service.update_admin(db, user_id, body, current))


@router.delete("/admins/{user_id}")
@audit_log(module="平台基础管理", action="删除管理员")
def delete_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    user_service.soft_delete_admin(db, user_id, current)
    return ok()


@router.put("/admins/{user_id}/status")
@audit_log(module="平台基础管理", action="变更管理员状态")
def set_admin_status(
    user_id: int,
    body: AdminStatusUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(user_service.set_admin_status(db, user_id, body.status, current))


@router.post("/admins/{user_id}/reset-password")
@audit_log(module="平台基础管理", action="重置管理员密码")
def reset_password(
    user_id: int,
    body: AdminResetPassword,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    user_service.reset_password(db, user_id, body.password)
    return ok()


# ---------- 角色 ----------
@router.get("/roles")
def list_roles(
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(role_service.list_roles(db, keyword))


@router.get("/roles/{role_id}")
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(role_service.get_role(db, role_id))


@router.post("/roles")
@audit_log(module="平台基础管理", action="新建角色")
def create_role(
    body: RoleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(role_service.create_role(db, body))


@router.put("/roles/{role_id}")
@audit_log(module="平台基础管理", action="编辑角色")
def update_role(
    role_id: int,
    body: RoleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(role_service.update_role(db, role_id, body))


@router.delete("/roles/{role_id}")
@audit_log(module="平台基础管理", action="删除角色")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    role_service.delete_role(db, role_id)
    return ok()


@router.put("/roles/{role_id}/status")
@audit_log(module="平台基础管理", action="变更角色状态")
def set_role_status(
    role_id: int,
    body: RoleStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.PLATFORM)),
):
    return ok(role_service.set_role_status(db, role_id, body.status))
