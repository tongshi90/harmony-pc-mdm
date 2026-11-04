"""设备远程控制：重启 / 关机 / 锁屏 / 数据擦除（MQTT DEVICE_CONTROL）."""

from __future__ import annotations

import json
import logging
import threading
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.enums.system_role import SYSTEM_ROLE_CODES
from app.models.device import Device
from app.models.role import SysRole
from app.models.user import User
from app.mqtt import publish_mqtt
from app.services.device_bind_service import unbind_device
from app.services.super_admin import is_builtin_super_admin
from app.utils.timeutil import now as local_now

logger = logging.getLogger("mdm.device.control")

CONTROL_REBOOT = "reboot"
CONTROL_SHUTDOWN = "shutDown"
CONTROL_LOCK = "lockScreen"
CONTROL_WIPE = "DISK_ERASURE"
ALLOWED_CONTROLS = frozenset(
    {CONTROL_REBOOT, CONTROL_SHUTDOWN, CONTROL_LOCK, CONTROL_WIPE}
)

MQTT_TYPE = "DEVICE_CONTROL"

# pending_disk_erasure：
#   0 无待办
#   1 云侧发送失败，待上线补发
#   2 已下发（retain），未完成确认；上线按库标记重推，稍后尝试清 Broker retain
PENDING_NONE = 0
PENDING_SEND = 1
PENDING_RETAIN = 2

# 上线检测到后延迟清 retain，给客户端留出订阅时间
_RETAIN_CLEAR_DELAY_SECONDS = 60
_clear_retain_lock = threading.Lock()
_clear_retain_scheduled: set[str] = set()


def can_disk_erasure(db: Session, user: User | None) -> bool:
    """内置 admin / is_admin / 系统角色 system_admin 可执行数据擦除."""
    if not user:
        return False
    if is_builtin_super_admin(user) or int(user.is_admin or 0) == 1:
        return True
    if not user.role_id:
        return False
    role = db.query(SysRole).filter(SysRole.id == user.role_id).first()
    if not role:
        return False
    code = (role.role_code or "").strip()
    return code == "system_admin" and code in SYSTEM_ROLE_CODES


def _build_payload(control_type: str) -> str:
    return json.dumps(
        {"type": MQTT_TYPE, "controlType": control_type},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _is_online(device: Device) -> bool:
    return int(device.status or 2) == 1


def _publish_control(
    sn: str, control_type: str, *, retain: bool = False
) -> tuple[bool, str]:
    try:
        publish_mqtt(
            sn=sn,
            message=_build_payload(control_type),
            qos=1,
            retain=retain,
        )
        return True, ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("设备控制 MQTT 失败 sn=%s type=%s: %s", sn, control_type, exc)
        return False, str(exc)


def _clear_retained_wipe(sn: str) -> tuple[bool, str]:
    """清除 Topic 上的 DISK_ERASURE 保留消息（空载荷 + retain=True）."""
    try:
        publish_mqtt(sn=sn, message="", qos=1, retain=True)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("清除数据擦除 retain 失败 sn=%s: %s", sn, exc)
        return False, str(exc)


def _device_still_online_in_broker(sn: str) -> bool | None:
    """查 EMQX 当前是否仍连接该 SN。

    Returns:
        True/False：查询成功时的在线结论；None：查询失败（调用方应保守跳过清除）。
    """
    try:
        from app.utils.mqtt_clients import query_connected_clients

        result = query_connected_clients()
        if not result.ok:
            logger.warning(
                "清 retain 前在线查询失败 sn=%s: %s", sn, result.message
            )
            return None
        online = {str(x).strip() for x in result.client_ids if str(x).strip()}
        return sn in online
    except Exception:  # noqa: BLE001
        logger.exception("清 retain 前在线查询异常 sn=%s", sn)
        return None


def _schedule_clear_retained_wipe(sn: str) -> None:
    """上线后延迟清除 Broker retain；清除前再次确认仍在线，避免假上线误清."""
    device_sn = (sn or "").strip()
    if not device_sn:
        return
    with _clear_retain_lock:
        if device_sn in _clear_retain_scheduled:
            return
        _clear_retain_scheduled.add(device_sn)

    def _job() -> None:
        try:
            time.sleep(_RETAIN_CLEAR_DELAY_SECONDS)
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                row = db.query(Device).filter(Device.sn == device_sn).first()
                if not row or int(row.pending_disk_erasure or 0) != PENDING_RETAIN:
                    return

                # 假上线 / 已掉线：不清 Broker、不改库标记，等待下次上线重推
                still = _device_still_online_in_broker(device_sn)
                if still is not True:
                    if still is False:
                        logger.info(
                            "延迟清除 retain 跳过（设备已不在线）sn=%s，保留 pending",
                            device_sn,
                        )
                    return

                ok, err = _clear_retained_wipe(device_sn)
                if ok:
                    row.pending_disk_erasure = PENDING_NONE
                    row.update_time = local_now()
                    db.commit()
                    logger.info("已清除数据擦除 retain sn=%s", device_sn)
                else:
                    # 清 Broker 失败：回退为待补发，避免以为已完成
                    row.pending_disk_erasure = PENDING_SEND
                    row.update_time = local_now()
                    db.commit()
                    logger.warning(
                        "延迟清除 retain 失败，已回退为待补发 sn=%s: %s",
                        device_sn,
                        err,
                    )
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception("延迟清除 retain 异常 sn=%s", device_sn)
            finally:
                db.close()
        finally:
            with _clear_retain_lock:
                _clear_retain_scheduled.discard(device_sn)

    threading.Thread(
        target=_job, name=f"clear-wipe-retain-{device_sn}", daemon=True
    ).start()


def control_device(db: Session, *, sn: str, control_type: str, operator: User) -> dict:
    ctype = (control_type or "").strip()
    if ctype not in ALLOWED_CONTROLS:
        raise HTTPException(status_code=400, detail="不支持的控制类型")

    device_sn = (sn or "").strip()
    if not device_sn:
        raise HTTPException(status_code=400, detail="请提供设备 SN")

    # 下发前尽量校准在线状态（与策略下发一致）
    try:
        from app.services.device_online_sync_service import sync_device_online_status

        sync_device_online_status(db)
    except Exception:  # noqa: BLE001
        logger.warning("设备控制前在线同步失败，继续使用本地状态 sn=%s", device_sn)

    device = db.query(Device).filter(Device.sn == device_sn).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    if ctype == CONTROL_WIPE:
        return _control_disk_erasure(db, device=device, operator=operator)

    # 重启 / 关机 / 锁屏：离线则忽略，不缓存
    if not _is_online(device):
        return {
            "sn": device_sn,
            "control_type": ctype,
            "delivered": False,
            "skipped": True,
            "pending": False,
            "message": "设备离线，指令未下发",
        }

    ok, err = _publish_control(device_sn, ctype)
    if not ok:
        return {
            "sn": device_sn,
            "control_type": ctype,
            "delivered": False,
            "skipped": True,
            "pending": False,
            "message": err or "MQTT 下发失败，指令未缓存",
        }
    return {
        "sn": device_sn,
        "control_type": ctype,
        "delivered": True,
        "skipped": False,
        "pending": False,
        "message": "指令已下发",
    }


def _control_disk_erasure(db: Session, *, device: Device, operator: User) -> dict:
    if not can_disk_erasure(db, operator):
        raise HTTPException(status_code=401, detail="无数据擦除权限，请联系系统管理员")

    device_sn = (device.sn or "").strip()
    was_bound = device.member_id is not None or int(device.bind_status or 0) == 1

    # 先解绑落库（不发 DEVICE_UNBINDING，改发 DISK_ERASURE）
    if was_bound:
        try:
            unbind_device(db, sn=device_sn, notify_mqtt=False)
        except HTTPException as exc:
            if exc.status_code != 400:
                raise

    device = db.query(Device).filter(Device.sn == device_sn).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")

    # 擦除一律 retain：不依赖「是否在线」判断，避免误判在线导致实时消息丢失且不重试。
    # 成功 → pending=2（库为真相，上线可重推）；失败 → pending=1。
    prefix = "已解绑；" if was_bound else ""
    online = _is_online(device)
    ok, err = _publish_control(device_sn, CONTROL_WIPE, retain=True)
    if ok:
        device.pending_disk_erasure = PENDING_RETAIN
        delivered = True
        pending = False
        if online:
            message = (
                f"{prefix}已下发数据擦除指令（已保留，上线可补推）"
                if prefix
                else "已下发数据擦除指令（已保留，上线可补推）"
            )
            # 当前已在线：安排延迟清 retain（清前会再确认仍在线）
            _schedule_clear_retained_wipe(device_sn)
        else:
            message = (
                f"{prefix}设备离线，擦除指令已保留在 Broker，上线后将按库标记补推"
                if prefix
                else "设备离线，擦除指令已保留在 Broker，上线后将按库标记补推"
            )
    else:
        device.pending_disk_erasure = PENDING_SEND
        delivered = False
        pending = True
        message = f"{prefix}指令发送失败，已缓存，上线后将自动补发"
        logger.warning("数据擦除 MQTT 失败已缓存 sn=%s: %s", device_sn, err)

    device.update_time = local_now()
    db.commit()

    return {
        "sn": device_sn,
        "control_type": CONTROL_WIPE,
        "delivered": delivered,
        "skipped": False,
        "pending": pending,
        "unbound": was_bound,
        "message": message,
    }


def flush_pending_disk_erasures(online_sns: list[str] | set[str] | None = None) -> int:
    """设备上线：凡库中仍有擦除待办（1/2），一律按库重发 retain，再安排清 Broker 保留.

    - pending=1：此前发送失败
    - pending=2：已发过，但 Broker 可能丢 retain / 设备尚未消费；以库为准再推一把
    """
    from app.database import SessionLocal

    sns = {str(x).strip() for x in (online_sns or []) if str(x).strip()}
    if not sns:
        return 0

    db = SessionLocal()
    sent = 0
    try:
        rows = (
            db.query(Device)
            .filter(
                Device.sn.in_(list(sns)),
                Device.pending_disk_erasure.in_([PENDING_SEND, PENDING_RETAIN]),
            )
            .all()
        )
        for device in rows:
            sn = (device.sn or "").strip()
            if not sn:
                continue
            prev = int(device.pending_disk_erasure or 0)
            ok, err = _publish_control(sn, CONTROL_WIPE, retain=True)
            if ok:
                device.pending_disk_erasure = PENDING_RETAIN
                device.update_time = local_now()
                sent += 1
                logger.info(
                    "上线按库重发数据擦除(retain) sn=%s prev_pending=%s",
                    sn,
                    prev,
                )
                _schedule_clear_retained_wipe(sn)
            else:
                # 保持/回退为待补发，下轮上线再试
                device.pending_disk_erasure = PENDING_SEND
                device.update_time = local_now()
                logger.warning("上线重发数据擦除失败 sn=%s: %s", sn, err)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("上线重发数据擦除异常")
    finally:
        db.close()
    return sent
