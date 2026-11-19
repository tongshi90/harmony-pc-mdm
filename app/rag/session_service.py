"""设备侧问答会话数据层（不进 RAG 核心）：建会话、取近 N 轮、落轮次。"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.department import SysMember
from app.models.device import Device
from app.rag.models import RagAskMessage, RagAskSession
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now

# 与管理台调试页近几轮上限对齐（轮≈一对 user/assistant）
MAX_HISTORY_TURNS = 2
MAX_HISTORY_MESSAGES = MAX_HISTORY_TURNS * 2


def require_bound_device(db: Session, sn: str) -> Device:
    """SN 必填且必须为已绑定设备，否则 HTTP 400。"""
    sn_v = (sn or "").strip()
    if not sn_v:
        raise HTTPException(status_code=400, detail="设备 SN 不能为空")
    device = db.query(Device).filter(Device.sn == sn_v).first()
    if device is None:
        raise HTTPException(status_code=400, detail="设备不存在，请先完成设备登记")
    member = None
    if device.member_id is not None:
        member = (
            db.query(SysMember)
            .filter(SysMember.id == int(device.member_id), SysMember.is_delete == 0)
            .first()
        )
    bound = bool(member) and int(device.bind_status or 0) == 1
    if not bound:
        raise HTTPException(
            status_code=400,
            detail="设备未绑定成员，请先完成绑定后再进行知识库问答",
        )
    return device


def create_session(db: Session, *, sn: str) -> RagAskSession:
    ts = now()
    row = RagAskSession(id=snowflake_id(), sn=sn.strip(), create_time=ts, update_time=ts)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_session_for_sn(db: Session, *, session_id: int | str, sn: str) -> RagAskSession:
    try:
        sid = int(str(session_id).strip())
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail="会话 ID 无效") from e
    sn_v = sn.strip()
    row = db.query(RagAskSession).filter(RagAskSession.id == sid).first()
    if row is None:
        raise HTTPException(status_code=400, detail="会话不存在或已失效，请重新发起对话")
    if (row.sn or "").strip() != sn_v:
        raise HTTPException(status_code=400, detail="会话与当前设备不匹配")
    return row


def load_recent_history(
    db: Session, *, session_id: int, limit_messages: int = MAX_HISTORY_MESSAGES
) -> list[dict[str, str]]:
    """按时间正序返回近 N 条消息，供核心改写/生成使用。"""
    rows = (
        db.query(RagAskMessage)
        .filter(RagAskMessage.session_id == int(session_id))
        .order_by(RagAskMessage.id.desc())
        .limit(max(1, int(limit_messages)))
        .all()
    )
    rows = list(reversed(rows))
    out: list[dict[str, str]] = []
    for r in rows:
        role = (r.role or "").strip()
        content = (r.content or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


def append_turn(
    db: Session,
    *,
    session_id: int,
    question: str,
    answer: str,
) -> None:
    """成功回答后写入本轮 user + assistant，并刷新会话时间。"""
    ts = now()
    q = (question or "").strip()
    a = (answer or "").strip()
    if q:
        db.add(
            RagAskMessage(
                id=snowflake_id(),
                session_id=int(session_id),
                role="user",
                content=q,
                create_time=ts,
            )
        )
    if a:
        db.add(
            RagAskMessage(
                id=snowflake_id(),
                session_id=int(session_id),
                role="assistant",
                content=a,
                create_time=ts,
            )
        )
    sess = db.query(RagAskSession).filter(RagAskSession.id == int(session_id)).first()
    if sess is not None:
        sess.update_time = ts
    db.commit()
