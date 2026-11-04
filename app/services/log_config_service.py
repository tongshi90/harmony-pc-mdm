from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.log_config import SysLogConfig
from app.models.op_log import SysOpLog
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now as local_now

logger = logging.getLogger("mdm.log_config")

DEFAULT_RETENTION_DAYS = 90


def ensure_config(db: Session) -> SysLogConfig:
    row = db.query(SysLogConfig).first()
    if row:
        return row
    row = SysLogConfig(
        id=snowflake_id(),
        retention_days=DEFAULT_RETENTION_DAYS,
        update_time=local_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _to_out(row: SysLogConfig) -> dict:
    return {
        "id": str(row.id),
        "retention_days": int(row.retention_days or DEFAULT_RETENTION_DAYS),
        "update_time": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else None,
    }


def get_config(db: Session) -> dict:
    return _to_out(ensure_config(db))


def update_config(db: Session, data) -> dict:
    days = int(data.retention_days)
    if days < 1 or days > 3650:
        raise HTTPException(status_code=400, detail="日志保留天数须在 1～3650 之间")
    row = ensure_config(db)
    row.retention_days = days
    row.update_time = local_now()
    db.commit()
    db.refresh(row)
    return _to_out(row)


def get_retention_days(db: Session) -> int:
    row = ensure_config(db)
    return max(1, int(row.retention_days or DEFAULT_RETENTION_DAYS))


def purge_expired_op_logs(db: Session | None = None) -> dict:
    """按保留天数物理删除 t_sys_op_log 中过期记录.

    仅清理管理员操作审计日志表，不影响其它业务数据。
    """
    from app.database import SessionLocal

    own = db is None
    if own:
        db = SessionLocal()
    try:
        days = get_retention_days(db)
        cutoff = local_now() - timedelta(days=days)
        deleted = (
            db.query(SysOpLog)
            .filter(SysOpLog.create_time < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        result = {
            "ok": True,
            "retention_days": days,
            "cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
            "deleted": int(deleted or 0),
        }
        logger.info(
            "[操作日志清理] 保留 %s 天 · 截止 %s · 删除 %s 条",
            days,
            result["cutoff"],
            result["deleted"],
        )
        return result
    except Exception:  # noqa: BLE001
        if db is not None:
            db.rollback()
        logger.exception("[操作日志清理] 失败")
        return {"ok": False, "deleted": 0, "message": "清理失败"}
    finally:
        if own and db is not None:
            db.close()
