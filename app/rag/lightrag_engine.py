"""LightRAG 进程内适配层。

入库：固定 ``LIGHTRAG_INGEST_BACKEND=rag_project`` + process_options ``!``（跳过图谱）。
提问：固定 ``mode=naive``（无图谱阶段）；逐库取候选切片 → 去重合并 → 可选 Rerank → 一次生成。

LightRAG 源码已内嵌于仓库根目录 ``lightrag/``（见 ``lightrag/VENDOR.md``），
不依赖本机外部 LightRAG 工程或 ``pip install -e``。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
import threading
from functools import partial
from pathlib import Path
from typing import Any

# 优先加载本仓 vendored 包，避免 site-packages / 残留 editable 抢先导入
_REPO_ROOT = Path(__file__).resolve().parents[2]
_repo_root_str = str(_REPO_ROOT)
if _repo_root_str in sys.path:
    sys.path.remove(_repo_root_str)
sys.path.insert(0, _repo_root_str)

from app.config import settings
from app.rag.paths import get_lightrag_root

logger = logging.getLogger("mdm.rag.lightrag")

# 进程级环境：必须在首次创建 LightRAG 实例前生效
os.environ.setdefault("LIGHTRAG_INGEST_BACKEND", "rag_project")
os.environ.setdefault(
    "EMBEDDING_BATCH_NUM",
    str(int(settings.rag_embedding_batch_size or 10) or 10),
)
# 切分器开关：与 Settings.rag_splitter / MDM_RAG_SPLITTER 对齐（ingest 内也会再读）
_splitter = (settings.rag_splitter or "split_v2").strip() or "split_v2"
os.environ.setdefault("MDM_RAG_SPLITTER", _splitter)
# LightRAG 从 INPUT_DIR/<workspace>/ 解析待处理文件；勿指向 upload，避免归档挪走原件
os.environ["INPUT_DIR"] = str(Path(get_lightrag_root()) / "inputs")

_lock = threading.Lock()
_instances: dict[str, Any] = {}
_init_locks: dict[str, asyncio.Lock] = {}


class _AsyncRunner:
    """单线程常驻事件环，避免多次 asyncio.run 导致 LightRAG 队列绑错 loop。"""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self.thread = threading.Thread(
            target=self._run, name="lightrag-loop", daemon=True
        )
        self.thread.start()
        self._ready.wait(timeout=30)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.loop.run_forever()

    def run(self, coro):
        if not self.thread.is_alive():
            raise RuntimeError("LightRAG 事件环线程已退出")
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return fut.result()


_runner: _AsyncRunner | None = None
_runner_lock = threading.Lock()


def _get_runner() -> _AsyncRunner:
    global _runner
    with _runner_lock:
        if _runner is None:
            _runner = _AsyncRunner()
        return _runner


def _workspace_name(kb_id: str | int) -> str:
    return f"kb_{kb_id}"


def _workspace_dir(kb_id: str | int) -> Path:
    root = Path(get_lightrag_root())
    path = root / _workspace_name(kb_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _workspace_inputs_dir(kb_id: str | int) -> Path:
    """LightRAG 可解析的入队文件目录：INPUT_DIR/<workspace>/。"""
    path = Path(get_lightrag_root()) / "inputs" / _workspace_name(kb_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stage_file_for_ingest(kb_id: str | int, file_path: str | Path) -> Path:
    """复制到 LightRAG inputs，保留 upload 原件（解析后可能被归档移动）。"""
    src = Path(file_path)
    if not src.is_file():
        raise FileNotFoundError(f"文件不存在: {src}")
    dest = _workspace_inputs_dir(kb_id) / src.name
    if dest.resolve() != src.resolve():
        shutil.copy2(src, dest)
    return dest


def _siliconflow_base_url() -> str:
    """从 app.config 的 chat/embedding URL 推导 OpenAI 兼容 base（…/v1）。"""
    for raw in (settings.rag_chat_url, settings.rag_embedding_url):
        url = (raw or "").strip().rstrip("/")
        if not url:
            continue
        if url.endswith("/chat/completions"):
            return url[: -len("/chat/completions")]
        if url.endswith("/embeddings"):
            return url[: -len("/embeddings")]
        if url.endswith("/v1"):
            return url
    raise RuntimeError(
        "无法从 MDM_RAG_CHAT_URL / MDM_RAG_EMBEDDING_URL 推导 base URL，请检查 app.config"
    )


def _api_key() -> str:
    return (settings.rag_siliconflow_api_key or "").strip()


def lightrag_doc_id_for_upload(file_path: str | Path) -> str:
    """与 LightRAG pending_parse 入队规则一致的 doc_id。"""
    from lightrag.utils import compute_mdhash_id
    from lightrag.utils_pipeline import normalize_document_file_path

    canonical = normalize_document_file_path(str(file_path))
    return compute_mdhash_id(canonical, prefix="doc-")


def _run_async(coro):
    """在同步上下文执行协程（统一打到常驻 LightRAG 事件环）。"""
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    # 已在 LightRAG 环内则直接 await 路径不可用（本函数供 sync 调用）；
    # 若误在环内调用，交给线程池再投递，避免死锁。
    if running is not None and running is _get_runner().loop:
        raise RuntimeError("勿在 LightRAG 事件环内同步调用 _run_async")
    return _get_runner().run(coro)


async def _build_rag(kb_id: str | int):
    from lightrag import LightRAG
    from lightrag.llm.openai import openai_complete_if_cache, openai_embed
    from lightrag.utils import EmbeddingFunc

    api_key = _api_key()
    if not api_key:
        raise RuntimeError("未配置 MDM_RAG_SILICONFLOW_API_KEY")

    base_url = _siliconflow_base_url()
    chat_model = settings.rag_chat_model
    embed_model = settings.rag_embedding_model
    embed_dim = int(settings.rag_embedding_dim or 2560)
    max_embed_tokens = int(settings.rag_embedding_max_tokens or 8192)
    workspace = _workspace_name(kb_id)
    working_dir = str(_workspace_dir(kb_id))

    async def llm_model_func(
        prompt,
        system_prompt=None,
        history_messages=None,
        keyword_extraction=False,
        **kwargs,
    ) -> str:
        return await openai_complete_if_cache(
            chat_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )

    rag = LightRAG(
        working_dir=working_dir,
        workspace=workspace,
        llm_model_func=llm_model_func,
        # openai_embed 已被装饰成 EmbeddingFunc(dim=1536)；必须用 .func 再包一层
        embedding_func=EmbeddingFunc(
            embedding_dim=embed_dim,
            max_token_size=max_embed_tokens,
            send_dimensions=True,
            model_name=embed_model,
            func=partial(
                openai_embed.func,
                model=embed_model,
                api_key=api_key,
                base_url=base_url,
            ),
        ),
        embedding_batch_num=int(settings.rag_embedding_batch_size or 10) or 10,
    )
    # 向量库额外保存切分关联字段（text_chunks KV 本身已存全量 dict）
    from app.rag.splitter.adapt import CHUNK_RELATION_FIELDS

    rag.chunks_vdb.meta_fields = set(rag.chunks_vdb.meta_fields or set()) | set(
        CHUNK_RELATION_FIELDS
    ) | {"full_doc_id", "content", "file_path"}
    await rag.initialize_storages()
    return rag


async def get_rag(kb_id: str | int):
    key = _workspace_name(kb_id)
    with _lock:
        if key not in _init_locks:
            _init_locks[key] = asyncio.Lock()
        init_lock = _init_locks[key]

    async with init_lock:
        with _lock:
            existing = _instances.get(key)
        if existing is not None:
            return existing
        rag = await _build_rag(kb_id)
        with _lock:
            _instances[key] = rag
        return rag


async def drop_rag_instance(kb_id: str | int) -> None:
    key = _workspace_name(kb_id)
    with _lock:
        rag = _instances.pop(key, None)
    if rag is not None:
        try:
            await rag.finalize_storages()
        except Exception:
            logger.exception("finalize LightRAG storages failed kb=%s", kb_id)


def purge_workspace_files(kb_id: str | int) -> None:
    """删除知识库对应 LightRAG 工作目录（向量/KV 等）。"""
    path = Path(get_lightrag_root()) / _workspace_name(kb_id)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


async def _read_doc_ingest_state(rag, doc_id: str) -> tuple[int, str, str]:
    """返回 (chunk_count, status_text, error_msg)。"""
    status = await rag.doc_status.get_by_id(doc_id)
    if not isinstance(status, dict):
        return 0, "", ""
    chunk_count = int(
        status.get("chunks_count") or len(status.get("chunks_list") or []) or 0
    )
    raw = status.get("status")
    status_text = raw.value if hasattr(raw, "value") else str(raw or "")
    err = str(status.get("error") or status.get("error_msg") or "")
    return chunk_count, status_text, err


async def _wait_ingest_chunks(
    rag,
    doc_id: str,
    *,
    timeout_sec: float = 600.0,
    interval_sec: float = 2.0,
) -> tuple[int, str]:
    """等待文档产出切片；pending/processing 时轮询，避免并发 busy 误判失败。"""
    import time

    deadline = time.monotonic() + max(1.0, timeout_sec)
    last_status = ""
    while True:
        chunk_count, status_text, err = await _read_doc_ingest_state(rag, doc_id)
        last_status = status_text or last_status
        st = (status_text or "").lower()
        if st in {"failed", "fail"}:
            raise RuntimeError(err or f"LightRAG 入库失败 status={status_text}")
        if chunk_count > 0 or st in {"processed", "completed"}:
            return chunk_count, status_text
        if time.monotonic() >= deadline:
            return chunk_count, last_status
        # 仍排队/处理中：再触发一次 process（空闲时会继续消化队列）
        if st in {"", "pending", "processing", "parsing", "preprocessed"}:
            try:
                await rag.apipeline_process_enqueue_documents()
            except Exception:
                logger.debug("wait 期间再次 process 失败 doc=%s", doc_id, exc_info=True)
        await asyncio.sleep(interval_sec)


async def ingest_file(
    *,
    kb_id: str | int,
    file_path: str | Path,
) -> dict[str, Any]:
    """上传文件入库：rag_project 切分 + chunk 向量化，跳过图谱。"""
    from lightrag.constants import (
        FULL_DOCS_FORMAT_PENDING_PARSE,
        PROCESS_OPTION_SKIP_KG,
    )

    staged = _stage_file_for_ingest(kb_id, file_path)
    rag = await get_rag(kb_id)
    doc_id = lightrag_doc_id_for_upload(staged)

    # 若同路径已存在则先删，支持失败重试/覆盖
    try:
        await rag.adelete_by_doc_id(doc_id, delete_llm_cache=True)
    except Exception:
        logger.debug("pre-delete doc %s skipped", doc_id, exc_info=True)

    await rag.apipeline_enqueue_documents(
        "",
        file_paths=str(staged.resolve()),
        docs_format=FULL_DOCS_FORMAT_PENDING_PARSE,
        process_options=PROCESS_OPTION_SKIP_KG,  # "!" 跳过实体/关系
    )
    await rag.apipeline_process_enqueue_documents()

    # 若管道当时 busy，process 可能立刻返回而文档仍 pending；轮询等待切片就绪
    chunk_count, status_text = await _wait_ingest_chunks(rag, doc_id)
    if chunk_count <= 0:
        raise RuntimeError(
            f"LightRAG 入库未产生切片 doc_id={doc_id} status={status_text}"
        )

    return {
        "doc_id": doc_id,
        "chunk_count": chunk_count,
        "status": status_text,
    }


async def delete_document(*, kb_id: str | int, file_path: str | Path) -> None:
    rag = await get_rag(kb_id)
    doc_id = lightrag_doc_id_for_upload(file_path)
    try:
        await rag.adelete_by_doc_id(doc_id, delete_llm_cache=True)
    except Exception:
        logger.exception("删除 LightRAG 文档失败 kb=%s doc=%s", kb_id, doc_id)
    try:
        from app.rag.splitter.sidecar import delete_chunk_sidecar

        delete_chunk_sidecar(doc_id)
    except Exception:
        logger.debug("删除 chunk sidecar 失败 doc=%s", doc_id, exc_info=True)


async def list_chunks(*, kb_id: str | int, file_path: str | Path) -> list[dict[str, Any]]:
    rag = await get_rag(kb_id)
    doc_id = lightrag_doc_id_for_upload(file_path)
    status = await rag.doc_status.get_by_id(doc_id)
    if not isinstance(status, dict):
        return []
    chunk_ids = list(status.get("chunks_list") or [])
    if not chunk_ids:
        return []
    rows = await rag.text_chunks.get_by_ids(chunk_ids)
    # get_by_ids 可能返回 list[dict] 或 dict
    items: list[dict[str, Any]] = []
    if isinstance(rows, dict):
        iterable = [(cid, rows.get(cid)) for cid in chunk_ids]
    else:
        iterable = list(zip(chunk_ids, rows or []))

    for cid, row in iterable:
        if not isinstance(row, dict):
            continue
        items.append(_format_chunk_row(str(cid), row))
    items.sort(key=lambda x: int(x.get("order") or 0))
    return items


def _format_chunk_row(cid: str, row: dict[str, Any]) -> dict[str, Any]:
    text = row.get("content") or ""
    order = row.get("chunk_order_index", 0)
    heading = row.get("heading") or {}
    title_path: list[str] = []
    if isinstance(heading, dict):
        parents = heading.get("parent_headings") or []
        leaf = heading.get("heading")
        title_path = [str(p) for p in parents if p] + ([str(leaf)] if leaf else [])
    stored_path = row.get("title_path")
    if isinstance(stored_path, list) and stored_path:
        title_path = [str(p) for p in stored_path if p]
    return {
        "chunk_id": cid,
        "order": int(order or 0),
        "text": text,
        "page": row.get("page"),
        "type": row.get("type") or "text",
        "length": len(text),
        "title_path": title_path,
        "doc_chunk_count": row.get("doc_chunk_count"),
        "doc_type": row.get("doc_type"),
        "parent_id": row.get("parent_id"),
        "parent_child_index": row.get("parent_child_index"),
        "parent_child_count": row.get("parent_child_count"),
        "prev_order": row.get("prev_order"),
        "next_order": row.get("next_order"),
        "section_title": row.get("section_title"),
        "route": row.get("route"),
        "manually_edited": bool(row.get("manually_edited")),
    }


async def update_chunk_content(
    *,
    kb_id: str | int,
    file_path: str | Path,
    chunk_id: str,
    content: str,
) -> dict[str, Any]:
    """更新单片正文并重新 Embedding，写回 text_chunks + chunks_vdb。"""
    text = (content or "").strip()
    if not text:
        raise ValueError("切片正文不能为空")
    if len(text) > 100_000:
        raise ValueError("切片正文过长（上限约 10 万字）")

    cid = str(chunk_id or "").strip()
    if not cid:
        raise ValueError("chunk_id 不能为空")

    rag = await get_rag(kb_id)
    doc_id = lightrag_doc_id_for_upload(file_path)
    status = await rag.doc_status.get_by_id(doc_id)
    if not isinstance(status, dict):
        raise ValueError("文件尚未入库完成，无法编辑切片")
    chunk_ids = [str(x) for x in (status.get("chunks_list") or []) if x]
    if cid not in chunk_ids:
        raise ValueError("切片不属于该文件或不存在")

    existing = await rag.text_chunks.get_by_id(cid)
    if not isinstance(existing, dict):
        raise ValueError("切片数据不存在")

    updated = dict(existing)
    updated["content"] = text
    updated["full_doc_id"] = doc_id
    if not updated.get("file_path"):
        updated["file_path"] = str(file_path)
    try:
        updated["tokens"] = len(rag.tokenizer.encode(text))
    except Exception:
        updated["tokens"] = max(1, len(text) // 2)
    updated["manually_edited"] = True

    await rag.text_chunks.upsert({cid: updated})
    await rag.chunks_vdb.upsert({cid: updated})
    await rag._flush_storages([rag.chunks_vdb, rag.text_chunks])

    order = updated.get("chunk_order_index")
    try:
        from app.rag.splitter.sidecar import patch_sidecar_chunk_text

        patch_sidecar_chunk_text(
            doc_id,
            order=int(order) if isinstance(order, int) else None,
            text=text,
        )
    except Exception:
        logger.debug("回写 chunk sidecar 失败 doc=%s chunk=%s", doc_id, cid, exc_info=True)

    return _format_chunk_row(cid, updated)


def update_chunk_content_sync(
    *,
    kb_id: str | int,
    file_path: str | Path,
    chunk_id: str,
    content: str,
) -> dict[str, Any]:
    return _run_async(
        update_chunk_content(
            kb_id=kb_id,
            file_path=file_path,
            chunk_id=chunk_id,
            content=content,
        )
    )


# P0-2：无有效召回时的固定拒答（禁止臆造制度内容）
NO_EVIDENCE_ANSWER = (
    "未在知识库中检索到与问题相关的制度内容，无法依据现有资料作答。"
    "请换一种问法，或确认相关文件已入库完成后再试。"
)

# P1-2：生成侧冲突处理约定
_ANSWER_SYSTEM_PROMPT = (
    "你是企业规章制度问答助手。只根据给定参考切片作答，禁止编造资料中没有的内容。"
    "若不同资料对同一事项的规定不一致，须并列说明各方表述差异，不要强行给出唯一结论。"
    "回答应准确、简洁，尽量贴近原文关键表述，按正常问答正文组织即可。"
    "正文中严禁出现任何与参考文献相关的标注：不要写文件名、知识库名、切片编号，"
    "不要加「来源」「依据」「参考」「见某某文件」等字样或括号脚注；"
    "不要在段末/行末附带出处，也不要在文末罗列来源列表——"
    "界面会单独展示参考依据，正文完全不要体现参考了哪份文件。"
)

# P3-2 / P3-1：历史上送与改写
_MAX_HISTORY_MESSAGES = 4  # 最近若干条（user/assistant），约 2 轮
_MAX_HISTORY_CHARS = 2000  # 单条截断，避免改写提示过长
_REWRITE_SYSTEM_PROMPT = (
    "你是企业规章制度问答助手的「问题改写」模块。"
    "根据对话历史，把用户当前这句话改写成一句语义完整、可独立检索的中文问句。"
    "规则："
    "1. 补全省略与指代（如「普通员工呢」需结合上文补全主题，例如上班时间/请假流程等）；"
    "2. 不要回答问题，只输出改写后的问句本身；"
    "3. 不要添加历史中未出现的新主题；"
    "4. 若当前句已完整独立，可原样输出或仅做轻微通顺化。"
)


def _chunk_text(c: dict[str, Any]) -> str:
    return (c.get("content") or c.get("text") or "").strip()


def _heading_chain(c: dict[str, Any]) -> list[str]:
    """从 heading / title_path 还原章节路径（父级…叶子）。"""
    heading = c.get("heading")
    if isinstance(heading, dict):
        parents = [
            str(p).strip()
            for p in (heading.get("parent_headings") or [])
            if str(p).strip()
        ]
        leaf = str(heading.get("heading") or "").strip()
        return parents + ([leaf] if leaf else [])
    title_path = c.get("title_path") or []
    if isinstance(title_path, list):
        return [str(p).strip() for p in title_path if str(p).strip()]
    return []


_CHAPTER_TITLE_LINE_RE = re.compile(
    r"^(?:"
    r"[一二三四五六七八九十百千两〇零\d]+[、．.]"  # 一、目的
    r"|第[一二三四五六七八九十百千两〇零\d]+[章节条款篇部分]"  # 第一章
    r"|[（(][一二三四五六七八九十百千两〇零\d]+[）)]"  # （一）
    r"|\d+(?:\.\d+)+\s*\S"  # 4.1信息安全小组
    r").*$"
)


def _source_display_text(c: dict[str, Any]) -> str:
    """参考原文展示用：完整分片正文，去掉章节面包屑/标题行，不截断。"""
    text = _chunk_text(c)
    if not text:
        return ""

    chain = _heading_chain(c)
    lines = text.split("\n")
    i = 0

    def _skip_blanks() -> None:
        nonlocal i
        while i < len(lines) and not lines[i].strip():
            i += 1

    _skip_blanks()
    if i >= len(lines):
        return ""

    first = lines[i].strip()
    crumb_candidates = set()
    if chain:
        crumb_candidates.add(" > ".join(chain))
        crumb_candidates.add(" → ".join(chain))

    # 1) 去掉 rag_project 注入的面包屑行：父级 > 叶子
    if first in crumb_candidates or " > " in first or " → " in first:
        if first in crumb_candidates or (chain and first.startswith(chain[0])):
            i += 1
            _skip_blanks()
        elif not chain:
            # 无元数据时，仍剥离明显的面包屑行，并据此推断章节链
            sep = " > " if " > " in first else " → "
            chain = [p.strip() for p in first.split(sep) if p.strip()]
            i += 1
            _skip_blanks()

    # 2) 正文开头若再重复父级/叶子标题，继续剥掉
    for h in chain:
        if i < len(lines) and lines[i].strip() == h:
            i += 1
            _skip_blanks()

    # 3) 无元数据的简单分片：首行是短章节标题时去掉
    if not chain and i < len(lines):
        head = lines[i].strip()
        if (
            head
            and len(head) <= 80
            and _CHAPTER_TITLE_LINE_RE.match(head)
            and i + 1 < len(lines)
        ):
            i += 1
            _skip_blanks()

    return "\n".join(lines[i:]).strip() or text


def _sources_from_tagged_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for c in chunks:
        kid = str(c.get("kb_id") or "")
        sources.append(
            {
                "chunk_id": c.get("chunk_id") or c.get("id"),
                "doc_id": c.get("full_doc_id") or c.get("doc_id"),
                "kb_id": kid,
                "text": _source_display_text(c),
                "page": c.get("page"),
                "rerank_score": c.get("rerank_score") or c.get("score"),
                "title_path": c.get("title_path") or [],
                "file_path": c.get("file_path"),
            }
        )
    return sources


def _dedupe_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in chunks:
        cid = str(c.get("chunk_id") or c.get("id") or "")
        kid = str(c.get("kb_id") or "")
        text = _chunk_text(c)
        key = f"{kid}:{cid}" if cid else f"{kid}:{hash(text[:200])}"
        if key in seen:
            continue
        if not text:
            continue
        seen.add(key)
        out.append(c)
    return out


def _hit_counts(chunks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in chunks:
        kid = str(c.get("kb_id") or "")
        if not kid:
            continue
        counts[kid] = counts.get(kid, 0) + 1
    return counts


async def _hydrate_chunks_from_text_store(
    rag: Any,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按 chunk_id 从 text_chunks 补回 full_doc_id / order / parent 等，供 Plan A/B 扩窗。

    LightRAG ``aquery_data`` → ``convert_to_user_format`` 只保留 content/file_path/chunk_id，
    入库时写入的关联字段会被剥掉；扩窗依赖这些字段加载侧车。
    """
    if not chunks:
        return []

    from app.rag.splitter.adapt import CHUNK_RELATION_FIELDS

    hydrate_fields = (
        "full_doc_id",
        "page",
        "tokens",
        "file_path",
    ) + tuple(CHUNK_RELATION_FIELDS)

    ids: list[str] = []
    for c in chunks:
        cid = str(c.get("chunk_id") or c.get("id") or "").strip()
        if cid:
            ids.append(cid)
    if not ids:
        return list(chunks)

    try:
        rows = await rag.text_chunks.get_by_ids(ids)
    except Exception:
        logger.exception("回填切片关联字段失败（text_chunks.get_by_ids）")
        return list(chunks)

    by_id: dict[str, dict[str, Any]] = {}
    for cid, row in zip(ids, rows or []):
        if isinstance(row, dict):
            by_id[cid] = row

    out: list[dict[str, Any]] = []
    for c in chunks:
        item = dict(c)
        cid = str(item.get("chunk_id") or item.get("id") or "").strip()
        if cid and not item.get("chunk_id"):
            item["chunk_id"] = cid
        full = by_id.get(cid) if cid else None
        if isinstance(full, dict):
            for key in hydrate_fields:
                if key not in full:
                    continue
                val = full.get(key)
                # parent/prev/next 允许为 None（表示无邻/无父），仍应写回
                if val is None and key not in (
                    "parent_id",
                    "prev_order",
                    "next_order",
                ):
                    continue
                # 检索结果已有路径时不覆盖
                if key == "file_path" and str(item.get(key) or "").strip():
                    continue
                item[key] = val
            # 兼容扩窗：有的路径只认 doc_id
            if item.get("full_doc_id") and not item.get("doc_id"):
                item["doc_id"] = item["full_doc_id"]
        out.append(item)
    return out


async def _retrieve_chunks_one(
    *,
    kb_id: str | int,
    question: str,
    candidate_k: int,
) -> list[dict[str, Any]]:
    """单库只检索切片，不生成答案（P1-1）。"""
    from lightrag import QueryParam

    rag = await get_rag(kb_id)
    param = QueryParam(
        mode="naive",
        top_k=candidate_k,
        chunk_top_k=candidate_k,
        enable_rerank=False,  # 跨库合并后再统一 rerank（P1-3）
        stream=False,
        only_need_context=True,
    )
    data = await rag.aquery_data(question, param)
    chunks: list[dict[str, Any]] = []
    if isinstance(data, dict) and data.get("status") == "success":
        chunks = list((data.get("data") or {}).get("chunks") or [])

    # LightRAG 返回的 chunks 缺关联字段；回填后再扩窗才认得出 Plan A/B
    hydrated = await _hydrate_chunks_from_text_store(rag, chunks)

    tagged: list[dict[str, Any]] = []
    for c in hydrated:
        item = dict(c)
        item["kb_id"] = str(kb_id)
        if not item.get("chunk_id") and item.get("id"):
            item["chunk_id"] = item.get("id")
        tagged.append(item)
    return tagged


async def _retrieve_across_kbs(
    *,
    question: str,
    kb_ids: list[str | int],
    candidate_k: int,
) -> list[dict[str, Any]]:
    all_chunks: list[dict[str, Any]] = []
    for kid in kb_ids:
        try:
            all_chunks.extend(
                await _retrieve_chunks_one(
                    kb_id=kid, question=question, candidate_k=candidate_k
                )
            )
        except Exception:
            logger.exception("知识库检索失败 kb=%s", kid)
    return all_chunks


async def _rerank_chunks(
    *,
    question: str,
    chunks: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """对合并后的候选切片做 SiliconFlow Rerank，取 top_k。"""
    if not chunks:
        return []
    if len(chunks) <= top_k:
        # 仍打分，便于调试展示
        pass

    documents = [_chunk_text(c) for c in chunks]
    try:
        from lightrag.rerank import cohere_rerank

        results = await cohere_rerank(
            query=question,
            documents=documents,
            top_n=min(top_k, len(documents)),
            api_key=_api_key(),
            model=settings.rag_rerank_model,
            base_url=settings.rag_rerank_url,
        )
    except Exception:
        logger.exception("Rerank 调用失败，回退向量顺序截断")
        return chunks[:top_k]

    if not results:
        return chunks[:top_k]

    out: list[dict[str, Any]] = []
    for item in results:
        idx = item.get("index")
        if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(chunks):
            continue
        c = dict(chunks[idx])
        c["rerank_score"] = item.get("relevance_score")
        out.append(c)
    return out[:top_k] if out else chunks[:top_k]


def _normalize_history(
    conversation_history: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """规范化历史上送：只保留 user/assistant，截断条数与长度，按时间正序。"""
    if not conversation_history:
        return []
    out: list[dict[str, str]] = []
    for item in conversation_history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if len(content) > _MAX_HISTORY_CHARS:
            content = content[:_MAX_HISTORY_CHARS] + "…"
        out.append({"role": role, "content": content})
    if len(out) > _MAX_HISTORY_MESSAGES:
        out = out[-_MAX_HISTORY_MESSAGES:]
    return out


async def _rewrite_question_for_retrieval(
    *,
    question: str,
    history: list[dict[str, str]],
) -> str:
    """P3-1：有历史上送时，把当前句改写成可独立检索的完整问句；失败则回退原问。"""
    q = (question or "").strip()
    if not q or not history:
        return q

    def _sync() -> str:
        from app.rag.model_config import get_text_splitter_llm

        lines = []
        for m in history:
            label = "用户" if m["role"] == "user" else "助手"
            lines.append(f"{label}：{m['content']}")
        user_prompt = (
            "对话历史：\n"
            + "\n".join(lines)
            + f"\n\n用户当前提问：{q}\n\n请输出改写后的完整问句："
        )
        try:
            llm = get_text_splitter_llm()
            raw = llm.chat(
                [
                    {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=256,
            )
        except Exception:
            logger.exception("问题改写调用失败")
            return q
        text = str(raw or "").strip()
        # 去掉可能的引号/前缀
        for prefix in ("改写后的问句：", "完整问句：", "问句："):
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
        text = text.strip("\"'“”")
        if not text or text.startswith("聊天API调用失败"):
            return q
        # 改写异常膨胀时回退
        if len(text) > max(400, len(q) * 8):
            return q
        return text

    return await asyncio.to_thread(_sync)


async def _split_sub_questions(question: str) -> list[str]:
    """P1-5：轻量 LLM 拆复合问；失败则原问一条。"""

    def _sync() -> list[str]:
        from app.rag.model_config import get_text_splitter_llm
        from app.rag.user_interaction.question_splitter import split_question

        try:
            subs = split_question(question, get_text_splitter_llm())
        except Exception:
            logger.exception("问题拆分失败")
            return [question]
        cleaned = [s.strip() for s in (subs or []) if s and str(s).strip()]
        if not cleaned:
            return [question]
        # 限制子问数量，避免检索爆炸
        return cleaned[:5]

    return await asyncio.to_thread(_sync)


def _build_answer_prompt(
    *,
    question: str,
    chunks: list[dict[str, Any]],
    kb_labels: dict[str, str] | None = None,
    sub_questions: list[str] | None = None,
    original_question: str | None = None,
) -> str:
    """组装生成 prompt（一次性 / 流式共用）。"""
    labels = kb_labels or {}
    blocks: list[str] = []
    for i, c in enumerate(chunks, 1):
        kid = str(c.get("kb_id") or "")
        label = labels.get(kid) or kid or "未知库"
        fpath = c.get("file_path") or "未知文件"
        blocks.append(
            f"【切片#{i}｜知识库：{label}｜文件：{fpath}】\n{_chunk_text(c)}"
        )

    sub_hint = ""
    if sub_questions and len(sub_questions) > 1:
        listed = "\n".join(f"- {sq}" for sq in sub_questions)
        sub_hint = f"\n本题可拆为以下子问题，请尽量逐项覆盖：\n{listed}\n"

    orig = (original_question or "").strip()
    orig_hint = ""
    if orig and orig != question:
        orig_hint = f"用户原始提问：{orig}\n"

    return (
        f"{orig_hint}"
        f"用户问题：{question}\n"
        f"{sub_hint}\n"
        "以下为检索到的制度参考切片（可能来自多个知识库），请据此作答。\n"
        "注意：切片标题中的知识库/文件名仅供你内部核对，"
        "正式回答正文中不要提及这些信息，也不要附加任何出处标注。\n\n"
        + "\n\n".join(blocks)
    )


def _history_messages(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    return [{"role": m["role"], "content": m["content"]} for m in (history or [])]


def _ask_empty_prepare(
    *,
    answer: str,
    kb_id: str | None,
    enable_rerank: bool,
    rewritten_question: str,
    original_question: str,
    sub_questions: list[str] | None = None,
    kb_hit_counts: dict | None = None,
    has_evidence: bool = False,
) -> dict[str, Any]:
    """无需再调 LLM 的准备结果（空库 / 无召回）。"""
    return {
        "needs_generation": False,
        "answer": answer,
        "kb_id": kb_id,
        "sub_questions": sub_questions or [],
        "sources": [],
        "chunks": [],
        "elapsed": None,
        "has_evidence": has_evidence,
        "kb_hit_counts": kb_hit_counts or {},
        "enable_rerank": enable_rerank,
        "original_question": original_question,
        "rewritten_question": rewritten_question,
        "history": [],
        "kb_labels": {},
    }


def _public_ask_fields(prepared: dict[str, Any]) -> dict[str, Any]:
    """接入层共用的公开字段（不含 chunks / history 等内部态）。"""
    return {
        "answer": prepared.get("answer") or "",
        "kb_id": prepared.get("kb_id"),
        "sub_questions": prepared.get("sub_questions") or [],
        "sources": prepared.get("sources") or [],
        "elapsed": prepared.get("elapsed"),
        "has_evidence": bool(prepared.get("has_evidence")),
        "kb_hit_counts": prepared.get("kb_hit_counts") or {},
        "enable_rerank": bool(prepared.get("enable_rerank")),
        "original_question": prepared.get("original_question") or "",
        "rewritten_question": prepared.get("rewritten_question") or "",
    }


async def prepare_ask(
    *,
    question: str,
    kb_ids: list[str | int],
    top_k: int = 5,
    kb_labels: dict[str, str] | None = None,
    enable_rerank: bool = True,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """检索准备：改写 → 拆问 → 逐库取切片 → 合并/Rerank。

    返回结构可供一次性生成或流式生成复用；``needs_generation=False`` 时已带固定 answer。
    """
    original_q = (question or "").strip()
    if not original_q:
        raise ValueError("问题不能为空")

    history = _normalize_history(conversation_history)
    rewritten_q = await _rewrite_question_for_retrieval(
        question=original_q, history=history
    )
    q = rewritten_q or original_q

    labels = kb_labels or {}
    if not kb_ids:
        return _ask_empty_prepare(
            answer=(
                "当前没有可检索的知识库（需至少有一个已入库完成的文件）。"
                "请先创建知识库并上传规章制度文件，待状态为「已完成」后再提问。"
            ),
            kb_id=None,
            enable_rerank=enable_rerank,
            rewritten_question=q,
            original_question=original_q,
        )

    top_k = max(1, min(int(top_k or 5), 20))
    candidate_k = max(top_k * 3, 10)

    sub_questions = await _split_sub_questions(q)
    queries = sub_questions if sub_questions else [q]

    raw_chunks: list[dict[str, Any]] = []
    for sq in queries:
        raw_chunks.extend(
            await _retrieve_across_kbs(
                question=sq, kb_ids=kb_ids, candidate_k=candidate_k
            )
        )

    merged = _dedupe_chunks(raw_chunks)
    retrieval_hits = _hit_counts(merged)
    kb_id_out = str(kb_ids[0]) if len(kb_ids) == 1 else None
    subs_out = sub_questions if len(sub_questions) > 1 else []

    if not merged:
        return _ask_empty_prepare(
            answer=NO_EVIDENCE_ANSWER,
            kb_id=kb_id_out,
            enable_rerank=enable_rerank,
            rewritten_question=q,
            original_question=original_q,
            sub_questions=subs_out,
            kb_hit_counts=retrieval_hits,
        )

    final_top = top_k
    if len(queries) > 1:
        final_top = min(top_k * len(queries), 20)

    if enable_rerank:
        selected = await _rerank_chunks(question=q, chunks=merged, top_k=final_top)
    else:
        selected = merged[:final_top]

    if not selected:
        return _ask_empty_prepare(
            answer=NO_EVIDENCE_ANSWER,
            kb_id=kb_id_out,
            enable_rerank=enable_rerank,
            rewritten_question=q,
            original_question=original_q,
            sub_questions=subs_out,
            kb_hit_counts=retrieval_hits,
        )

    # 提问侧回挂：父块 / 邻域扩窗仅影响生成上下文；参考依据仍用命中小片
    try:
        from app.rag.splitter.context_expand import expand_chunks_for_generation

        context_chunks = expand_chunks_for_generation(selected)
    except Exception:
        logger.exception("上下文回挂失败，回退命中小片")
        context_chunks = selected

    return {
        "needs_generation": True,
        "answer": "",
        "kb_id": kb_id_out,
        "sub_questions": subs_out,
        "sources": _sources_from_tagged_chunks(selected),
        "chunks": context_chunks,
        "elapsed": None,
        "has_evidence": True,
        "kb_hit_counts": _hit_counts(selected),
        "enable_rerank": enable_rerank,
        "original_question": original_q,
        "rewritten_question": q,
        "history": history,
        "kb_labels": labels,
    }


async def generate_answer(prepared: dict[str, Any]) -> str:
    """基于 prepare_ask 结果一次性生成完整回答。"""
    if not prepared.get("needs_generation"):
        return str(prepared.get("answer") or "")

    from lightrag.llm.openai import openai_complete_if_cache

    prompt = _build_answer_prompt(
        question=str(prepared.get("rewritten_question") or ""),
        chunks=list(prepared.get("chunks") or []),
        kb_labels=prepared.get("kb_labels") or {},
        sub_questions=prepared.get("sub_questions") or None,
        original_question=prepared.get("original_question"),
    )
    answer = await openai_complete_if_cache(
        settings.rag_chat_model,
        prompt,
        system_prompt=_ANSWER_SYSTEM_PROMPT,
        history_messages=_history_messages(prepared.get("history")),
        api_key=_api_key(),
        base_url=_siliconflow_base_url(),
        stream=False,
    )
    return str(answer or "") if not isinstance(answer, str) else answer


async def generate_answer_stream(prepared: dict[str, Any]):
    """基于 prepare_ask 结果流式产出文本增量（async generator）。"""
    if not prepared.get("needs_generation"):
        text = str(prepared.get("answer") or "")
        if text:
            yield text
        return

    from lightrag.llm.openai import openai_complete_if_cache

    prompt = _build_answer_prompt(
        question=str(prepared.get("rewritten_question") or ""),
        chunks=list(prepared.get("chunks") or []),
        kb_labels=prepared.get("kb_labels") or {},
        sub_questions=prepared.get("sub_questions") or None,
        original_question=prepared.get("original_question"),
    )
    result = await openai_complete_if_cache(
        settings.rag_chat_model,
        prompt,
        system_prompt=_ANSWER_SYSTEM_PROMPT,
        history_messages=_history_messages(prepared.get("history")),
        api_key=_api_key(),
        base_url=_siliconflow_base_url(),
        stream=True,
    )
    if hasattr(result, "__aiter__"):
        async for chunk in result:
            if chunk is None:
                continue
            text = chunk if isinstance(chunk, str) else str(chunk)
            if text:
                yield text
    else:
        text = str(result or "")
        if text:
            yield text


# -------- 同步包装（供 service 后台线程 / 同步路由调用） --------

def ingest_file_sync(*, kb_id: str | int, file_path: str | Path) -> dict[str, Any]:
    return _run_async(ingest_file(kb_id=kb_id, file_path=file_path))


def delete_document_sync(*, kb_id: str | int, file_path: str | Path) -> None:
    _run_async(delete_document(kb_id=kb_id, file_path=file_path))


def list_chunks_sync(*, kb_id: str | int, file_path: str | Path) -> list[dict[str, Any]]:
    return _run_async(list_chunks(kb_id=kb_id, file_path=file_path))


def prepare_ask_sync(
    *,
    question: str,
    kb_ids: list[str | int],
    top_k: int = 5,
    kb_labels: dict[str, str] | None = None,
    enable_rerank: bool = True,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _run_async(
        prepare_ask(
            question=question,
            kb_ids=kb_ids,
            top_k=top_k,
            kb_labels=kb_labels,
            enable_rerank=enable_rerank,
            conversation_history=conversation_history,
        )
    )


def drop_workspace_sync(kb_id: str | int) -> None:
    _run_async(drop_rag_instance(kb_id))
    purge_workspace_files(kb_id)
