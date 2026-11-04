"""设备管理（/platform/device）."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.schemas.common import ok
from app.schemas.device import DeviceBatchCreateIn, DeviceCreateIn
from app.schemas.device_control import DeviceControlIn
from app.services import device_biz_card_service, device_control_service, device_service

router = APIRouter(dependencies=[Depends(require_menu(MenuCode.DEVICE))])


@router.get("")
def list_devices(
    keyword: str | None = Query(None),
    status: str | None = Query(None, description="online|offline|lost"),
    bind: str | None = Query(None, description="bound|unbound"),
    compliance: str | None = Query(
        None, description="compliant|noncompliant（按 t_device.is_compliant）"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    return ok(
        device_service.list_devices(
            db,
            keyword=keyword,
            status=status,
            bind=bind,
            compliance=compliance,
            page=page,
            page_size=page_size,
        )
    )


@router.post("")
@audit_log(module="设备管理", action="登记设备")
def create_device(
    body: DeviceCreateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    """预登记单台设备（仅 SN）."""
    return ok(device_service.create_device(db, body.sn))


@router.post("/batch")
@audit_log(module="设备管理", action="批量登记设备")
def batch_create_devices(
    body: DeviceBatchCreateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    """批量预登记；部分失败不回滚，返回成功/失败明细."""
    return ok(device_service.batch_create_devices(db, body.sns))


@router.get("/{sn}")
def get_device(
    sn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    return ok(device_service.get_device(db, sn))


@router.delete("/{sn}")
@audit_log(module="设备管理", action="删除设备")
def delete_device(
    sn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    """删除未绑定设备；已绑定设备返回 400."""
    device_service.delete_device(db, sn)
    return ok()


@router.get("/{sn}/snapshot")
def get_device_snapshot(
    sn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    return ok(device_service.get_device_snapshot(db, sn))


@router.get("/{sn}/apps")
def list_device_apps(
    sn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    return ok(device_service.list_installed_apps(db, sn))


@router.get("/{sn}/locations")
def list_device_locations(
    sn: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    """设备轨迹（位置上报日志）分页列表."""
    return ok(
        device_service.list_location_logs(
            db, sn, page=page, page_size=page_size
        )
    )


@router.get("/{sn}/biz-cards")
def list_device_biz_cards(
    sn: str,
    kind: str = Query(
        ...,
        description="mine=我的提交（含终态）；todo=待我审核（仅 PENDING）",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    """设备绑定成员的业务卡片列表（我的提交 / 待我审核）."""
    return ok(
        device_biz_card_service.list_device_biz_cards(
            db, sn, kind=kind, page=page, page_size=page_size
        )
    )


@router.get("/{sn}/biz-cards/{biz_id}")
def get_device_biz_card_detail(
    sn: str,
    biz_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    """业务卡片详情：完整审批步骤与当前进度."""
    return ok(device_biz_card_service.get_device_biz_card_detail(db, sn, biz_id))


@router.post("/{sn}/strategy-pull")
@audit_log(module="设备管理", action="补发策略拉取")
def notify_strategy_pull(
    sn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    """不合规设备：MQTT 补发 STRATEGY_PULL，通知端侧重新拉取预期策略."""
    return ok(device_service.notify_strategy_pull(db, sn))


@router.post("/{sn}/snapshot-report")
@audit_log(module="设备管理", action="催设备上报")
def notify_snapshot_report(
    sn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    """已绑定设备：MQTT SNAPSHOT_REPORT，催端侧上报基本信息、已装应用与策略快照."""
    return ok(device_service.notify_snapshot_report(db, sn))


@router.post("/{sn}/unbind")
@audit_log(module="设备管理", action="管理员解绑设备")
def unbind_device(
    sn: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.DEVICE)),
):
    """管理台解绑：清绑定与策略相关数据，并向设备发 DEVICE_UNBINDING（仅管理员侧）."""
    from app.services import device_bind_service

    return ok(device_bind_service.unbind_device(db, sn=sn))


@router.post("/{sn}/control")
@audit_log(module="设备管理", action="设备远程控制")
def control_device(
    sn: str,
    body: DeviceControlIn,
    db: Session = Depends(get_db),
    current: User = Depends(require_menu(MenuCode.DEVICE)),
):
    """远程控制：reboot / shutDown / lockScreen / DISK_ERASURE（MQTT DEVICE_CONTROL）."""
    return ok(
        device_control_service.control_device(
            db,
            sn=sn,
            control_type=body.control_type,
            operator=current,
        )
    )
