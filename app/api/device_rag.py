"""对外设备侧 · 知识库问答（/api/rag/* 白名单，无需登录）."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import no_audit
from app.rag import service as rag_service
from app.rag.schemas import DeviceAskRequest
from app.schemas.common import ok

router = APIRouter(prefix="/rag", tags=["设备侧-知识库问答"])


@router.post("/ask")
@no_audit
def ask(body: DeviceAskRequest, db: Session = Depends(get_db)):
    """设备侧制度问答（一次性 JSON）。

    传参：``sn``/``SN`` + ``question`` 必填；``sessionId`` 可空（空=新会话）。
    须为已绑定设备；云侧按会话取近几轮历史，响应带回 ``sessionId``。
    """
    data = rag_service.ask_for_device(
        db,
        question=body.question,
        sn=body.resolved_sn(),
        session_id=body.resolved_session_id() or None,
    )
    return ok(data)
