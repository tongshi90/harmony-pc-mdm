"""RAG 管理台接口：/platform/rag/*（需登录 + 菜单 rag）."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.decorators.audit import audit_log, no_audit
from app.deps import require_menu
from app.enums.menu import MenuCode
from app.models.user import User
from app.rag import service as rag_service
from app.rag.schemas import (
    AskRequest,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    RagChunkUpdate,
)
from app.schemas.common import ok

router = APIRouter(dependencies=[Depends(require_menu(MenuCode.RAG))])


@router.get("/knowledge-bases")
def list_knowledge_bases(
    keyword: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    return ok(rag_service.list_knowledge_bases(db, keyword))


@router.post("/knowledge-bases")
@audit_log(module="知识库", action="新建知识库")
def create_knowledge_base(
    body: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    return ok(
        rag_service.create_knowledge_base(
            db, name=body.name, description=body.description
        )
    )


@router.get("/knowledge-bases/{kb_id}")
def get_knowledge_base(
    kb_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    return ok(rag_service.get_knowledge_base(db, kb_id))


@router.put("/knowledge-bases/{kb_id}")
@audit_log(module="知识库", action="编辑知识库")
def update_knowledge_base(
    kb_id: str,
    body: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    return ok(
        rag_service.update_knowledge_base(
            db, kb_id, name=body.name, description=body.description
        )
    )


@router.delete("/knowledge-bases/{kb_id}")
@audit_log(module="知识库", action="删除知识库")
def delete_knowledge_base(
    kb_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    rag_service.delete_knowledge_base(db, kb_id)
    return ok(True)


@router.get("/knowledge-bases/{kb_id}/files")
def list_files(
    kb_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    return ok(rag_service.list_files(db, kb_id, page=page, page_size=page_size))


@router.post("/knowledge-bases/{kb_id}/files/upload")
@audit_log(module="知识库", action="上传知识文件")
async def upload_file(
    kb_id: str,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    """支持批量：form 字段 ``files`` 多文件；兼容旧客户端单字段 ``file``。"""
    upload_list: list[UploadFile] = []
    if files:
        upload_list.extend([f for f in files if f is not None])
    if file is not None:
        upload_list.append(file)
    if not upload_list:
        raise HTTPException(status_code=400, detail="请选择要上传的文件")
    items = await rag_service.upload_files(db, kb_id, upload_list)
    # 仅旧单字段 file 时返回对象；带 files（含批量）统一返回列表
    if file is not None and not files:
        return ok(items[0])
    return ok(items)


@router.delete("/knowledge-bases/{kb_id}/files/{file_id}")
@audit_log(module="知识库", action="删除知识文件")
def delete_file(
    kb_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    rag_service.delete_file(db, kb_id, file_id)
    return ok(True)


@router.get("/knowledge-bases/{kb_id}/files/{file_id}/chunks")
def list_chunks(
    kb_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    return ok(rag_service.list_file_chunks(db, kb_id, file_id))


@router.put("/knowledge-bases/{kb_id}/files/{file_id}/chunks/{chunk_id}")
@audit_log(module="知识库", action="编辑知识切片")
def update_chunk(
    kb_id: str,
    file_id: str,
    chunk_id: str,
    body: RagChunkUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    """编辑单条切片正文，保存后对该片重新 Embedding。"""
    return ok(
        rag_service.update_file_chunk(
            db, kb_id, file_id, chunk_id, text=body.text
        )
    )


@router.post("/ask")
@audit_log(module="知识库", action="调试提问")
def ask(
    body: AskRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    """一次性 JSON（保留；与未来设备 API 字段同构，便于复用核心）。"""
    history = None
    if body.conversation_history:
        history = [m.model_dump() for m in body.conversation_history]
    return ok(
        rag_service.ask(
            db,
            question=body.question,
            kb_id=body.kb_id,
            top_k=body.top_k,
            enable_rerank=body.enable_rerank,
            conversation_history=history,
        )
    )


@router.post("/ask/stream")
@no_audit
async def ask_stream(
    body: AskRequest,
    _: User = Depends(require_menu(MenuCode.RAG)),
):
    """管理台对话 SSE 流式输出。

    事件：status / meta / answer_delta / final / error / done。
    final.data 与 POST /ask 的 data 同构。不经审计中间件缓冲，以免假流式。
    """
    history = None
    if body.conversation_history:
        history = [m.model_dump() for m in body.conversation_history]
    return StreamingResponse(
        rag_service.ask_sse_events(
            question=body.question,
            kb_id=body.kb_id,
            top_k=body.top_k,
            enable_rerank=body.enable_rerank,
            conversation_history=history,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
