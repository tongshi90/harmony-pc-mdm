"""RAG 管理台业务：知识库分组、文件入库、调试提问."""

from __future__ import annotations

import logging
import queue
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.rag.models import RagFile, RagKnowledgeBase
from app.rag.paths import get_upload_path
from app.utils.snowflake import snowflake_id
from app.utils.timeutil import now

logger = logging.getLogger("mdm.rag")

# 上传支持 PDF / Word / PPT；.doc→.docx、.ppt→.pptx 在入库前自动转换
SUPPORTED_EXTS = {".pdf", ".docx", ".doc", ".pptx", ".ppt"}
_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_PPTX_MIME = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
STATUS_PARSING = "parsing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# 同知识库入库串行队列：避免 LightRAG pipeline busy 导致后传文件误报 pending
_ingest_lock = threading.Lock()
_ingest_queues: dict[str, queue.Queue] = {}
_ingest_workers: dict[str, threading.Thread] = {}


def _fmt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _kb_out(row: RagKnowledgeBase, *, file_count: int = 0) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description or "",
        "file_count": file_count,
        "create_time": _fmt(row.create_time),
        "update_time": _fmt(row.update_time),
    }


def _file_out(row: RagFile) -> dict:
    return {
        "id": str(row.id),
        "kb_id": str(row.kb_id),
        "name": row.name,
        "file_type": row.file_type,
        "file_size": row.file_size,
        "status": row.status,
        "error_message": row.error_message or "",
        "chunk_count": row.chunk_count or 0,
        "create_time": _fmt(row.create_time),
        "update_time": _fmt(row.update_time),
    }


def _get_kb(db: Session, kb_id: int | str) -> RagKnowledgeBase:
    kid = int(kb_id)
    row = db.query(RagKnowledgeBase).filter(RagKnowledgeBase.id == kid).first()
    if not row:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return row


def _get_file(db: Session, file_id: int | str) -> RagFile:
    fid = int(file_id)
    row = db.query(RagFile).filter(RagFile.id == fid).first()
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")
    return row


def _file_counts(db: Session) -> dict[int, int]:
    from sqlalchemy import func

    rows = (
        db.query(RagFile.kb_id, func.count(RagFile.id))
        .group_by(RagFile.kb_id)
        .all()
    )
    return {int(kb_id): int(cnt) for kb_id, cnt in rows}


def list_knowledge_bases(db: Session, keyword: str | None = None) -> list[dict]:
    q = db.query(RagKnowledgeBase)
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        q = q.filter(
            (RagKnowledgeBase.name.like(kw))
            | (RagKnowledgeBase.description.like(kw))
        )
    rows = q.order_by(RagKnowledgeBase.create_time.desc()).all()
    counts = _file_counts(db)
    return [_kb_out(r, file_count=counts.get(int(r.id), 0)) for r in rows]


def get_knowledge_base(db: Session, kb_id: int | str) -> dict:
    row = _get_kb(db, kb_id)
    counts = _file_counts(db)
    return _kb_out(row, file_count=counts.get(int(row.id), 0))


def create_knowledge_base(db: Session, *, name: str, description: str | None) -> dict:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="知识库名称不能为空")
    exists = (
        db.query(RagKnowledgeBase)
        .filter(RagKnowledgeBase.name == name)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="知识库名称已存在")
    ts = now()
    row = RagKnowledgeBase(
        id=snowflake_id(),
        name=name,
        description=(description or "").strip() or None,
        create_time=ts,
        update_time=ts,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _kb_out(row, file_count=0)


def update_knowledge_base(
    db: Session, kb_id: int | str, *, name: str | None, description: str | None
) -> dict:
    row = _get_kb(db, kb_id)
    if name is not None:
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="知识库名称不能为空")
        dup = (
            db.query(RagKnowledgeBase)
            .filter(RagKnowledgeBase.name == name, RagKnowledgeBase.id != row.id)
            .first()
        )
        if dup:
            raise HTTPException(status_code=400, detail="知识库名称已存在")
        row.name = name
    if description is not None:
        row.description = description.strip() or None
    row.update_time = now()
    db.commit()
    db.refresh(row)
    counts = _file_counts(db)
    return _kb_out(row, file_count=counts.get(int(row.id), 0))


def delete_knowledge_base(db: Session, kb_id: int | str) -> None:
    row = _get_kb(db, kb_id)
    files = db.query(RagFile).filter(RagFile.kb_id == row.id).all()
    for f in files:
        _delete_file_assets(f)
        db.delete(f)
    db.delete(row)
    db.commit()
    try:
        from app.rag.lightrag_engine import drop_workspace_sync

        drop_workspace_sync(row.id)
    except Exception:
        logger.exception("清理 LightRAG workspace 失败 kb_id=%s", row.id)


def list_files(
    db: Session,
    kb_id: int | str,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    _get_kb(db, kb_id)
    kid = int(kb_id)
    q = db.query(RagFile).filter(RagFile.kb_id == kid)
    total = q.count()
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    rows = (
        q.order_by(RagFile.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_file_out(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _delete_file_assets(row: RagFile) -> None:
    try:
        from app.rag.lightrag_engine import delete_document_sync

        delete_document_sync(kb_id=row.kb_id, file_path=row.file_path)
    except Exception:
        logger.exception("删除 LightRAG 文档失败 file_id=%s", row.id)
    try:
        p = Path(row.file_path)
        # .doc/.ppt 入库前会转成同名 .docx/.pptx；删除时两边都清掉
        siblings = {p}
        suf = p.suffix.lower()
        if suf == ".docx":
            siblings.add(p.with_suffix(".doc"))
        elif suf == ".doc":
            siblings.add(p.with_suffix(".docx"))
        elif suf == ".pptx":
            siblings.add(p.with_suffix(".ppt"))
        elif suf == ".ppt":
            siblings.add(p.with_suffix(".pptx"))
        for path in siblings:
            if path.is_file():
                path.unlink()
    except Exception:
        logger.exception("删除本地文件失败 path=%s", row.file_path)


def delete_file(db: Session, kb_id: int | str, file_id: int | str) -> None:
    _get_kb(db, kb_id)
    row = _get_file(db, file_id)
    if int(row.kb_id) != int(kb_id):
        raise HTTPException(status_code=404, detail="文件不在该知识库中")
    _delete_file_assets(row)
    db.delete(row)
    db.commit()


async def upload_files(
    db: Session, kb_id: int | str, files: list[UploadFile]
) -> list[dict]:
    """批量上传：落盘并入同库串行解析队列，立即返回 parsing 状态列表。"""
    if not files:
        raise HTTPException(status_code=400, detail="请选择要上传的文件")

    kb = _get_kb(db, kb_id)
    upload_dir = Path(get_upload_path())
    upload_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = int(settings.rag_max_upload_bytes or 0) or (32 * 1024 * 1024)
    out_rows: list[RagFile] = []

    for file in files:
        filename = (file.filename or "").strip()
        if not filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"仅支持 PDF / Word / PPT"
                    f"（.pdf .docx .doc .pptx .ppt）：{filename}"
                ),
            )

        file_id = snowflake_id()
        dest = upload_dir / f"{file_id}{ext}"
        size = 0
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"文件过大，上限 {max_bytes // (1024 * 1024)}MB："
                            f"{filename}"
                        ),
                    )
                out.write(chunk)

        mime = {
            ".pdf": "application/pdf",
            ".docx": _DOCX_MIME,
            ".doc": "application/msword",
            ".pptx": _PPTX_MIME,
            ".ppt": "application/vnd.ms-powerpoint",
        }.get(ext, file.content_type or "application/octet-stream")

        ts = now()
        row = RagFile(
            id=file_id,
            kb_id=kb.id,
            name=filename,
            file_type=mime,
            file_size=size,
            file_path=str(dest),
            status=STATUS_PARSING,
            error_message=None,
            chunk_count=0,
            create_time=ts,
            update_time=ts,
        )
        db.add(row)
        out_rows.append(row)

    db.commit()
    for row in out_rows:
        db.refresh(row)
        _enqueue_ingest(str(row.file_path), str(row.id), str(kb.id))

    return [_file_out(r) for r in out_rows]


def _ensure_ingest_worker(kb_id: str) -> queue.Queue:
    key = str(kb_id)
    with _ingest_lock:
        q = _ingest_queues.get(key)
        if q is None:
            q = queue.Queue()
            _ingest_queues[key] = q
        worker = _ingest_workers.get(key)
        if worker is None or not worker.is_alive():
            worker = threading.Thread(
                target=_ingest_worker_loop,
                args=(key,),
                daemon=True,
                name=f"rag-ingest-worker-{key}",
            )
            _ingest_workers[key] = worker
            worker.start()
            logger.info("RAG 入库 worker 已启动 kb=%s", key)
        return q


def _enqueue_ingest(file_path: str, file_id: str, kb_id: str) -> None:
    q = _ensure_ingest_worker(kb_id)
    q.put((file_path, file_id, str(kb_id)))
    logger.info(
        "RAG 入库已排队 file_id=%s kb=%s queue_size=%s",
        file_id,
        kb_id,
        q.qsize(),
    )


def _ingest_local_path_exists(row: RagFile) -> bool:
    """判断入库用本地文件是否还在（含 .doc↔.docx / .ppt↔.pptx 转换产物）。"""
    p = Path(row.file_path or "")
    candidates = {p}
    suf = p.suffix.lower()
    if suf == ".docx":
        candidates.add(p.with_suffix(".doc"))
    elif suf == ".doc":
        candidates.add(p.with_suffix(".docx"))
    elif suf == ".pptx":
        candidates.add(p.with_suffix(".ppt"))
    elif suf == ".ppt":
        candidates.add(p.with_suffix(".pptx"))
    return any(c.is_file() for c in candidates if str(c))


def resume_interrupted_ingests() -> dict[str, int]:
    """方案 A：启动时把仍为 parsing 的任务重新入队；本地文件丢失则标失败。

    重新入队前清空 parse_start_time，避免把崩溃前的解析时长算进超时。
    """
    from app.database import SessionLocal

    requeued = 0
    marked_failed = 0
    db = SessionLocal()
    try:
        rows = (
            db.query(RagFile)
            .filter(RagFile.status == STATUS_PARSING)
            .order_by(RagFile.id.asc())
            .all()
        )
        for row in rows:
            if not _ingest_local_path_exists(row):
                row.status = STATUS_FAILED
                row.error_message = humanize_ingest_error(
                    "服务重启后发现本地上传文件已丢失，无法继续解析。请重新上传该文件。"
                )[:2000]
                row.parse_start_time = None
                row.update_time = now()
                marked_failed += 1
                continue
            # 排队等待阶段不计超时
            row.parse_start_time = None
            row.error_message = None
            row.update_time = now()
            db.flush()
            _enqueue_ingest(str(row.file_path), str(row.id), str(row.kb_id))
            requeued += 1
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("RAG 启动恢复入库队列失败")
        raise
    finally:
        db.close()

    if requeued or marked_failed:
        logger.info(
            "RAG 启动恢复入库：requeued=%s failed_missing_file=%s",
            requeued,
            marked_failed,
        )
    return {"requeued": requeued, "failed_missing_file": marked_failed}


def fail_timed_out_ingests() -> int:
    """方案 D：对已正式开始解析且超时的 parsing 文件标失败。

    仅看 parse_start_time；仍为 None 表示还在排队，不超时。
    """
    from app.database import SessionLocal

    timeout_sec = max(60, int(settings.rag_ingest_timeout_seconds or 7200))
    cutoff = now() - timedelta(seconds=timeout_sec)
    db = SessionLocal()
    failed = 0
    try:
        rows = (
            db.query(RagFile)
            .filter(
                RagFile.status == STATUS_PARSING,
                RagFile.parse_start_time.isnot(None),
                RagFile.parse_start_time < cutoff,
            )
            .all()
        )
        for row in rows:
            started = row.parse_start_time
            row.status = STATUS_FAILED
            row.error_message = humanize_ingest_error(
                f"入库超时（已超过 {timeout_sec // 60} 分钟仍未完成；"
                f"超时从正式开始解析起算，排队等待不计）。"
                f"请删除后重新上传，或检查模型服务与文件是否过大。"
            )[:2000]
            row.update_time = now()
            failed += 1
            logger.warning(
                "RAG 入库超时失败 file_id=%s name=%s parse_start=%s",
                row.id,
                row.name,
                started,
            )
        if failed:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        logger.exception("RAG 入库超时巡检失败")
    finally:
        db.close()
    return failed


def _ingest_worker_loop(kb_key: str) -> None:
    """按知识库串行消费入库任务。"""
    q = _ingest_queues[kb_key]
    while True:
        item = q.get()
        try:
            if item is None:
                break
            file_path, file_id, kb_id = item
            logger.info(
                "RAG 入库开始处理 file_id=%s kb=%s remaining=%s",
                file_id,
                kb_id,
                q.qsize(),
            )
            _process_document_job(file_path, file_id, kb_id)
        except Exception:
            logger.exception("RAG 入库 worker 异常 kb=%s", kb_key)
        finally:
            q.task_done()


def _ensure_docx_for_ingest(row: RagFile, file_path: str) -> str:
    """若为 .doc：用 msdoc2docx 转为同目录 .docx，并回写元数据。返回最终入库路径。"""
    path = Path(file_path)
    if path.suffix.lower() != ".doc":
        return str(path)

    from app.rag.office_convert import convert_doc_to_docx

    docx_path = convert_doc_to_docx(path, dest=path.with_suffix(".docx"))
    row.file_path = str(docx_path)
    row.file_type = _DOCX_MIME
    try:
        row.file_size = int(docx_path.stat().st_size)
    except OSError:
        pass
    # 展示名仍保留用户上传的 .doc 名；解析用 file_path 指向 .docx
    logger.info(
        "RAG .doc 已转 .docx file_id=%s src=%s dest=%s",
        row.id,
        path.name,
        docx_path.name,
    )
    return str(docx_path)


def _ensure_pptx_for_ingest(row: RagFile, file_path: str) -> str:
    """若为 .ppt：用 ppt2pptx 转为同目录 .pptx，并回写元数据。返回最终入库路径。"""
    path = Path(file_path)
    if path.suffix.lower() != ".ppt":
        return str(path)

    from app.rag.office_convert import convert_ppt_to_pptx

    pptx_path = convert_ppt_to_pptx(path, dest=path.with_suffix(".pptx"))
    row.file_path = str(pptx_path)
    row.file_type = _PPTX_MIME
    try:
        row.file_size = int(pptx_path.stat().st_size)
    except OSError:
        pass
    logger.info(
        "RAG .ppt 已转 .pptx file_id=%s src=%s dest=%s",
        row.id,
        path.name,
        pptx_path.name,
    )
    return str(pptx_path)


def _prepare_ingest_path(row: RagFile, file_path: str) -> str:
    """入库前统一转换旧版 Office 二进制格式。"""
    path = _ensure_docx_for_ingest(row, file_path)
    return _ensure_pptx_for_ingest(row, path)


def humanize_ingest_error(exc: BaseException | str) -> str:
    """把入库异常整理成管理台可读的中文原因（含处置建议）。"""
    raw = str(exc or "").strip()
    if not raw:
        return "解析失败，原因未知。请删除后重试，或联系管理员查看服务日志。"

    low = raw.lower()

    if "扫描版" in raw or "扫描件" in raw or "scanned" in low:
        return (
            "判定为扫描版 PDF（几乎抽不出可选中文字），暂不支持入库。"
            "请换成可选中复制文字的文本型 PDF，或先 OCR 后再上传。"
        )

    if (
        "mdm_rag_siliconflow_api_key" in low
        or "未配置 mdm_rag_siliconflow_api_key" in low
        or "无法向量化" in raw
    ):
        return (
            "未配置向量化所需的 SiliconFlow API Key（环境变量 "
            "MDM_RAG_SILICONFLOW_API_KEY），无法完成入库。请管理员配置后重试。"
        )

    if "ppt2pptx" in low or (".ppt" in low and ("转" in raw or "convert" in low)):
        return (
            "旧版 .ppt 转 .pptx 失败。"
            "请先在本机另存为 .pptx 后再上传，或检查是否已安装 ppt2pptx。"
        )

    if "msdoc2docx" in low or (
        ".doc" in low and ("转" in raw or "convert" in low) and "docx" in low
    ):
        return (
            "旧版 .doc 转 .docx 失败。"
            "请先在 Word 中另存为 .docx 后再上传，或检查是否已安装 msdoc2docx。"
        )

    if "不支持的文件类型" in raw or "unsupported" in low:
        return (
            "文件类型不受支持。"
            "当前仅支持 PDF / Word / PPT（.pdf .docx .doc .pptx .ppt）。"
        )

    if "no usable text" in low or "extracted no usable" in low or "无可用文本" in raw:
        return (
            "未能从文件中提取出可用正文，无法入库。"
            "请确认文件不是空文档/纯图片页，或换一份可复制文字的文本型文件。"
        )

    if "filenotfound" in low or "文件不存在" in raw or "no such file" in low:
        return "本地上传文件已丢失，无法继续解析。请重新上传该文件。"

    if "401" in raw or "unauthorized" in low or "invalid api key" in low:
        return (
            "调用模型服务鉴权失败（API Key 无效或过期）。"
            "请管理员检查 MDM_RAG_SILICONFLOW_API_KEY 后重试。"
        )

    if (
        "402" in raw
        or "insufficient" in low
        or "account balance" in low
        or "余额不足" in raw
        or "arrearage" in low
    ):
        return (
            "SiliconFlow 账户余额不足，无法完成向量化入库。"
            "请到 SiliconFlow 控制台充值后，删除该文件并重新上传。"
        )

    if "429" in raw or "rate limit" in low or "too many requests" in low:
        return "模型服务请求过于频繁被限流。请稍后再试，或减少同时入库的文件数量。"

    if "timeout" in low or "timed out" in low or "超时" in raw:
        return "调用模型或网络超时。请稍后重试；若文件很大可拆分后再上传。"

    if "connection" in low or "connect" in low or "网络" in raw:
        return "无法连接模型服务。请检查服务器网络与 SiliconFlow 服务是否可用后重试。"

    # 已是较短中文提示则直接用；过长则截断并保留原文前缀
    cleaned = " ".join(raw.split())
    if len(cleaned) > 280:
        cleaned = cleaned[:280] + "…"
    if any("\u4e00" <= ch <= "\u9fff" for ch in cleaned):
        return cleaned
    return f"解析失败：{cleaned}"


def _process_document_job(file_path: str, file_id: str, kb_id: str) -> None:
    from app.database import SessionLocal
    from app.rag.lightrag_engine import ingest_file_sync

    db = SessionLocal()
    try:
        row = db.query(RagFile).filter(RagFile.id == int(file_id)).first()
        if not row:
            return
        # 已被超时巡检标失败 / 用户删除后重传等：跳过陈旧队列项
        if row.status != STATUS_PARSING:
            logger.info(
                "RAG 跳过非 parsing 任务 file_id=%s status=%s",
                file_id,
                row.status,
            )
            return
        if not (settings.rag_siliconflow_api_key or "").strip():
            row.status = STATUS_FAILED
            row.error_message = humanize_ingest_error(
                "未配置 MDM_RAG_SILICONFLOW_API_KEY，无法向量化"
            )
            row.parse_start_time = None
            row.update_time = now()
            db.commit()
            return

        # 正式开始解析：超时从此刻起算（批量上传排队等待不计）
        row.parse_start_time = now()
        row.update_time = now()
        db.commit()

        try:
            ingest_path = _prepare_ingest_path(row, file_path)
            # 转换后的路径写回库，避免切片查询仍指向 .doc/.ppt
            db.commit()
            result = ingest_file_sync(kb_id=kb_id, file_path=ingest_path)
            # 可能被超时巡检并行标失败：以当前库状态为准
            db.refresh(row)
            if row.status != STATUS_PARSING:
                logger.warning(
                    "RAG 入库完成但状态已非 parsing，跳过写成功 file_id=%s status=%s",
                    file_id,
                    row.status,
                )
                return
            row.status = STATUS_COMPLETED
            row.chunk_count = int((result or {}).get("chunk_count") or 0)
            row.error_message = None
            row.update_time = now()
            db.commit()
        except Exception as e:
            logger.exception("RAG 入库失败 file_id=%s", file_id)
            db.refresh(row)
            if row.status != STATUS_PARSING:
                return
            row.status = STATUS_FAILED
            row.error_message = humanize_ingest_error(e)[:2000]
            row.update_time = now()
            db.commit()
    finally:
        db.close()


def list_file_chunks(db: Session, kb_id: int | str, file_id: int | str) -> dict:
    _get_kb(db, kb_id)
    row = _get_file(db, file_id)
    if int(row.kb_id) != int(kb_id):
        raise HTTPException(status_code=404, detail="文件不在该知识库中")
    from app.rag.lightrag_engine import list_chunks_sync

    try:
        formatted = list_chunks_sync(kb_id=row.kb_id, file_path=row.file_path)
    except Exception as e:
        logger.exception("读取切片失败 file_id=%s", file_id)
        raise HTTPException(status_code=500, detail=f"读取切片失败: {e}") from e
    return {"items": formatted, "total": len(formatted)}


def update_file_chunk(
    db: Session,
    kb_id: int | str,
    file_id: int | str,
    chunk_id: str,
    *,
    text: str,
) -> dict:
    """编辑单片正文并重新向量化。"""
    _get_kb(db, kb_id)
    row = _get_file(db, file_id)
    if int(row.kb_id) != int(kb_id):
        raise HTTPException(status_code=404, detail="文件不在该知识库中")
    if row.status != STATUS_COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="仅「已完成」的文件可编辑切片，请等待入库完成或先处理失败文件",
        )
    if not (settings.rag_siliconflow_api_key or "").strip():
        raise HTTPException(
            status_code=400,
            detail="未配置 MDM_RAG_SILICONFLOW_API_KEY，无法重新向量化",
        )

    from app.rag.lightrag_engine import update_chunk_content_sync

    try:
        updated = update_chunk_content_sync(
            kb_id=row.kb_id,
            file_path=row.file_path,
            chunk_id=chunk_id,
            content=text,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception(
            "更新切片失败 file_id=%s chunk_id=%s", file_id, chunk_id
        )
        raise HTTPException(
            status_code=500,
            detail=humanize_ingest_error(e)[:500],
        ) from e

    row.update_time = now()
    db.commit()
    return updated


def _kb_completed_file_counts(db: Session) -> dict[int, int]:
    from sqlalchemy import func

    rows = (
        db.query(RagFile.kb_id, func.count(RagFile.id))
        .filter(RagFile.status == STATUS_COMPLETED)
        .group_by(RagFile.kb_id)
        .all()
    )
    return {int(kb_id): int(cnt) for kb_id, cnt in rows}


def _ask_notices_and_scope(
    db: Session, *, kb_id: int | str | None
) -> tuple[list[int], list[str], dict[str, str]]:
    """P0-4/P0-5：确定可问知识库列表，并生成未就绪提示。

    Returns:
        searchable_kb_ids, notices, kb_labels(id->name)
    """
    notices: list[str] = []
    completed_counts = _kb_completed_file_counts(db)

    if kb_id is not None and str(kb_id).strip():
        kb = _get_kb(db, kb_id)
        kid = int(kb.id)
        kb_labels = {str(kid): kb.name}
        files = db.query(RagFile).filter(RagFile.kb_id == kid).all()
        n_parsing = sum(1 for f in files if f.status == STATUS_PARSING)
        n_failed = sum(1 for f in files if f.status == STATUS_FAILED)
        n_done = completed_counts.get(kid, 0)
        if n_parsing:
            notices.append(
                f"知识库「{kb.name}」有 {n_parsing} 个文件正在入库，完成前无法被检索。"
            )
        if n_failed:
            notices.append(
                f"知识库「{kb.name}」有 {n_failed} 个文件入库失败，请删除后重新上传。"
            )
        if n_done <= 0:
            notices.append(
                f"知识库「{kb.name}」暂无已入库完成的文件，请先上传并等待处理完成。"
            )
            return [], notices, kb_labels
        return [kid], notices, kb_labels

    # 全库：只查至少有 1 个 completed 文件的库
    all_kbs = (
        db.query(RagKnowledgeBase)
        .order_by(RagKnowledgeBase.create_time.desc())
        .all()
    )
    kb_labels = {str(int(r.id)): r.name for r in all_kbs}
    searchable = [int(r.id) for r in all_kbs if completed_counts.get(int(r.id), 0) > 0]
    skipped = [r for r in all_kbs if completed_counts.get(int(r.id), 0) <= 0]

    n_parsing = db.query(RagFile).filter(RagFile.status == STATUS_PARSING).count()
    n_failed = db.query(RagFile).filter(RagFile.status == STATUS_FAILED).count()
    if n_parsing:
        notices.append(f"当前有 {n_parsing} 个文件正在入库，完成前无法被检索。")
    if n_failed:
        notices.append(
            f"当前有 {n_failed} 个文件入库失败，需删除后重新上传才可检索。"
        )
    if skipped:
        names = "、".join(r.name for r in skipped[:5])
        if len(skipped) > 5:
            notices.append(
                f"以下知识库暂无已完成文件，已跳过：{names} 等共 {len(skipped)} 个。"
            )
        else:
            notices.append(f"以下知识库暂无已完成文件，已跳过：{names}。")
    if not searchable:
        notices.append("没有可检索的知识库，请先上传文件并等待入库完成。")

    return searchable, notices, kb_labels


def _enrich_sources(
    db: Session,
    sources: list[dict[str, Any]],
    *,
    kb_labels: dict[str, str],
) -> list[dict[str, Any]]:
    """P0-3：为 sources 补齐知识库名、原文件名、file_id。"""
    if not sources:
        return []

    files = db.query(RagFile).all()
    by_basename: dict[str, RagFile] = {}
    by_id: dict[str, RagFile] = {}
    for f in files:
        by_id[str(f.id)] = f
        try:
            by_basename[Path(f.file_path).name] = f
        except Exception:
            pass

    out: list[dict[str, Any]] = []
    for s in sources:
        item = dict(s)
        kid = str(item.get("kb_id") or "")
        item["kb_name"] = kb_labels.get(kid) or item.get("kb_name") or ""

        basename = Path(str(item.get("file_path") or "")).name
        row = by_basename.get(basename) if basename else None
        if row is None:
            # 兼容仅有 doc_id / 其它形态
            doc_id = str(item.get("doc_id") or "")
            row = by_id.get(doc_id)

        if row is not None:
            item["file_id"] = str(row.id)
            item["file_name"] = row.name
            item["kb_id"] = str(row.kb_id)
            item["kb_name"] = kb_labels.get(str(row.kb_id)) or item["kb_name"]
            if not item.get("file_path"):
                item["file_path"] = Path(row.file_path).name
        else:
            item.setdefault("file_id", None)
            item.setdefault("file_name", basename or "")

        out.append(item)
    return out


def _normalize_ask_history(
    conversation_history: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not conversation_history:
        return None
    return [
        {"role": str(m.get("role") or ""), "content": str(m.get("content") or "")}
        for m in conversation_history
        if isinstance(m, dict)
    ]


def _finalize_ask_payload(
    db: Session,
    *,
    prepared: dict[str, Any],
    notices: list[str],
    kb_ids: list[int],
    kb_labels: dict[str, str],
    answer: str | None = None,
) -> dict[str, Any]:
    """把引擎 prepare/生成结果整理为管理台/未来设备 API 同构的 data。"""
    from app.rag.lightrag_engine import _public_ask_fields

    public = _public_ask_fields(prepared)
    if answer is not None:
        public["answer"] = answer
    sources = _enrich_sources(db, public.get("sources") or [], kb_labels=kb_labels)
    hit_counts = public.get("kb_hit_counts") or {}
    hit_labeled = {
        (kb_labels.get(str(kid)) or str(kid)): int(cnt)
        for kid, cnt in hit_counts.items()
    }
    public["sources"] = sources
    public["notices"] = notices
    public["searched_kb_ids"] = [str(i) for i in kb_ids]
    public["kb_hit_labels"] = hit_labeled
    return public


def prepare_ask_result(
    db: Session,
    *,
    question: str,
    kb_id: int | str | None = None,
    top_k: int = 5,
    enable_rerank: bool = True,
    conversation_history: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[str], list[int], dict[str, str]]:
    """检索准备（含 notices / 源文件 enrich）。供一次性与流式共用。"""
    q = (question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="问题不能为空")
    if not (settings.rag_siliconflow_api_key or "").strip():
        raise HTTPException(
            status_code=400,
            detail="未配置 MDM_RAG_SILICONFLOW_API_KEY，无法提问",
        )

    history_payload = _normalize_ask_history(conversation_history)
    kb_ids, notices, kb_labels = _ask_notices_and_scope(db, kb_id=kb_id)

    from app.rag.lightrag_engine import NO_EVIDENCE_ANSWER, prepare_ask_sync

    if not kb_ids:
        prepared = {
            "needs_generation": False,
            "answer": (
                NO_EVIDENCE_ANSWER
                if (kb_id is not None and str(kb_id).strip())
                else (
                    "当前没有可检索的知识库（需至少有一个已入库完成的文件）。"
                    "请先上传规章制度文件，待状态为「已完成」后再提问。"
                )
            ),
            "kb_id": str(kb_id) if kb_id is not None and str(kb_id).strip() else None,
            "sub_questions": [],
            "sources": [],
            "chunks": [],
            "elapsed": None,
            "has_evidence": False,
            "kb_hit_counts": {},
            "enable_rerank": enable_rerank,
            "original_question": q,
            "rewritten_question": q,
            "history": [],
            "kb_labels": kb_labels,
        }
        return prepared, notices, kb_ids, kb_labels

    try:
        prepared = prepare_ask_sync(
            question=q,
            kb_ids=kb_ids,
            top_k=top_k,
            kb_labels=kb_labels,
            enable_rerank=enable_rerank,
            conversation_history=history_payload,
        )
    except Exception as e:
        logger.exception("RAG 提问准备失败")
        raise HTTPException(status_code=500, detail=str(e)[:2000]) from e

    prepared["kb_labels"] = kb_labels
    return prepared, notices, kb_ids, kb_labels


def ask(
    db: Session,
    *,
    question: str,
    kb_id: int | str | None = None,
    top_k: int = 5,
    enable_rerank: bool = True,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """管理台一次性提问（与未来设备 API 同构 data）。"""
    from app.rag.lightrag_engine import generate_answer

    prepared, notices, kb_ids, kb_labels = prepare_ask_result(
        db,
        question=question,
        kb_id=kb_id,
        top_k=top_k,
        enable_rerank=enable_rerank,
        conversation_history=conversation_history,
    )
    answer = prepared.get("answer") or ""
    if prepared.get("needs_generation"):
        try:
            # generate 不依赖 LightRAG 实例，可在任意事件环调用；经 sync 包装投递
            from app.rag.lightrag_engine import _run_async

            answer = _run_async(generate_answer(prepared))
        except Exception as e:
            logger.exception("RAG 生成失败")
            raise HTTPException(status_code=500, detail=str(e)[:2000]) from e

    return _finalize_ask_payload(
        db,
        prepared=prepared,
        notices=notices,
        kb_ids=kb_ids,
        kb_labels=kb_labels,
        answer=answer,
    )


def _trim_sources_for_device(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """设备侧参考依据：去掉调试噪音，保留展示与溯源必要字段。"""
    out: list[dict[str, Any]] = []
    for s in sources or []:
        out.append(
            {
                "file_id": s.get("file_id"),
                "file_name": s.get("file_name") or "",
                "file_path": s.get("file_path") or "",
                "kb_id": s.get("kb_id"),
                "kb_name": s.get("kb_name") or "",
                "page": s.get("page"),
                "text": s.get("text") or "",
                "chunk_id": s.get("chunk_id"),
            }
        )
    return out


def ask_for_device(
    db: Session,
    *,
    question: str,
    sn: str,
    session_id: str | int | None = None,
) -> dict[str, Any]:
    """设备侧接入：校验绑定 SN → 会话历史 → 调核心 ask → 落库轮次。

    管理台调试不走此方法（不落会话）。核心层仍只接收 question + history。
    """
    from app.rag import session_service as rag_session

    q = (question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="问题不能为空")

    device = rag_session.require_bound_device(db, sn)
    sn_v = device.sn

    sid_raw = "" if session_id is None else str(session_id).strip()
    history: list[dict[str, Any]] | None = None
    session = None
    if sid_raw:
        session = rag_session.get_session_for_sn(db, session_id=sid_raw, sn=sn_v)
        history = rag_session.load_recent_history(db, session_id=int(session.id))
        if not history:
            history = None

    # 先走核心生成；新会话在成功后再建，避免失败留下空会话
    full = ask(
        db,
        question=q,
        kb_id=None,
        top_k=5,
        enable_rerank=True,
        conversation_history=history,
    )
    answer = full.get("answer") or ""

    if session is None:
        session = rag_session.create_session(db, sn=sn_v)
    session_id_out = str(session.id)
    try:
        rag_session.append_turn(
            db,
            session_id=int(session.id),
            question=q,
            answer=answer,
        )
    except Exception:
        logger.exception("设备问答落库失败 session_id=%s sn=%s", session_id_out, sn_v)
        # 回答已生成：仍返回给端，避免因落库失败导致端侧无答案
        db.rollback()

    return {
        "answer": answer,
        "sources": _trim_sources_for_device(full.get("sources") or []),
        "has_evidence": bool(full.get("has_evidence")),
        "notices": full.get("notices") or [],
        "original_question": full.get("original_question") or q,
        "rewritten_question": full.get("rewritten_question") or q,
        "sub_questions": full.get("sub_questions") or [],
        "sn": sn_v,
        "sessionId": session_id_out,
    }


async def ask_sse_events(
    *,
    question: str,
    kb_id: int | str | None = None,
    top_k: int = 5,
    enable_rerank: bool = True,
    conversation_history: list[dict[str, Any]] | None = None,
):
    """管理台 SSE 事件流：status / meta / answer_delta / final / error / done。

    使用独立 DB Session 做检索准备，避免与请求线程共享 Session。
    """
    import asyncio
    import json

    from app.database import SessionLocal
    from app.rag.lightrag_engine import generate_answer_stream

    def _sse(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _prepare_with_own_db():
        db = SessionLocal()
        try:
            return prepare_ask_result(
                db,
                question=question,
                kb_id=kb_id,
                top_k=top_k,
                enable_rerank=enable_rerank,
                conversation_history=conversation_history,
            )
        finally:
            db.close()

    yield _sse("status", {"phase": "retrieving", "message": "正在检索…"})
    try:
        prepared, notices, kb_ids, kb_labels = await asyncio.to_thread(
            _prepare_with_own_db
        )
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        yield _sse("error", {"message": detail})
        yield _sse("done", {})
        return
    except Exception as e:
        logger.exception("RAG 流式准备失败")
        yield _sse("error", {"message": str(e)[:2000]})
        yield _sse("done", {})
        return

    db = SessionLocal()
    try:
        enriched_sources = _enrich_sources(
            db, prepared.get("sources") or [], kb_labels=kb_labels
        )
        prepared["sources"] = enriched_sources

        yield _sse(
            "meta",
            {
                "original_question": prepared.get("original_question") or "",
                "rewritten_question": prepared.get("rewritten_question") or "",
                "sub_questions": prepared.get("sub_questions") or [],
                "has_evidence": bool(prepared.get("has_evidence")),
                "needs_generation": bool(prepared.get("needs_generation")),
            },
        )

        parts: list[str] = []
        if not prepared.get("needs_generation"):
            text = str(prepared.get("answer") or "")
            if text:
                parts.append(text)
                yield _sse("answer_delta", {"text": text})
        else:
            yield _sse("status", {"phase": "generating", "message": "正在生成回答…"})
            try:
                async for delta in generate_answer_stream(prepared):
                    if not delta:
                        continue
                    parts.append(delta)
                    yield _sse("answer_delta", {"text": delta})
            except Exception as e:
                logger.exception("RAG 流式生成失败")
                yield _sse("error", {"message": str(e)[:2000]})
                yield _sse("done", {})
                return

        final = _finalize_ask_payload(
            db,
            prepared=prepared,
            notices=notices,
            kb_ids=kb_ids,
            kb_labels=kb_labels,
            answer="".join(parts),
        )
        yield _sse("final", final)
        yield _sse("done", {})
    finally:
        db.close()
