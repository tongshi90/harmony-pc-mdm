"""切分关系侧车：parent/prev/next/route 按 doc_id 落盘。

路径：``data/rag/lightrag/chunk_meta/{doc_id}.json``
提问回挂与调试可读；不改 LightRAG 向量库 schema。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.rag.paths import get_lightrag_root

logger = logging.getLogger("mdm.rag.splitter.sidecar")


def chunk_meta_dir() -> Path:
    path = Path(get_lightrag_root()) / "chunk_meta"
    path.mkdir(parents=True, exist_ok=True)
    return path


def chunk_meta_path(doc_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(doc_id))
    return chunk_meta_dir() / f"{safe}.json"


def save_chunk_sidecar(doc_id: str, payload: dict[str, Any]) -> Path:
    path = chunk_meta_path(doc_id)
    data = dict(payload or {})
    data["doc_id"] = str(doc_id)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "chunk sidecar saved doc=%s chunks=%s path=%s",
        doc_id,
        data.get("chunk_count"),
        path,
    )
    return path


def load_chunk_sidecar(doc_id: str) -> dict[str, Any] | None:
    if not doc_id:
        return None
    path = chunk_meta_path(doc_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("读取 chunk sidecar 失败 doc=%s", doc_id)
        return None
    return raw if isinstance(raw, dict) else None


def delete_chunk_sidecar(doc_id: str) -> None:
    path = chunk_meta_path(doc_id)
    try:
        if path.is_file():
            path.unlink()
    except Exception:
        logger.debug("删除 chunk sidecar 失败 doc=%s", doc_id, exc_info=True)


def _append_dedupe_overlap(base: str, nxt: str) -> str:
    """拼接两段文本，去掉窗间 overlap。"""
    a = (base or "").strip()
    b = (nxt or "").strip()
    if not a:
        return b
    if not b:
        return a
    if b in a:
        return a
    if a in b:
        return b
    max_k = min(len(a), len(b))
    for k in range(max_k, 0, -1):
        if a.endswith(b[:k]):
            return (a + b[k:]).strip()
    return f"{a}\n\n{b}".strip()


def join_texts_dedupe_overlap(parts: list[str]) -> str:
    out = ""
    for p in parts:
        t = (p or "").strip()
        if not t:
            continue
        out = _append_dedupe_overlap(out, t)
    return out


def rebuild_parent_content(
    payload: dict[str, Any],
    parent_id: str,
) -> bool:
    """按同父子片现文重算 parents[].content（去 overlap）。"""
    pid = str(parent_id or "").strip()
    if not payload or not pid:
        return False

    parent: dict[str, Any] | None = None
    for p in payload.get("parents") or []:
        if isinstance(p, dict) and str(p.get("parent_id") or "") == pid:
            parent = p
            break
    if parent is None:
        return False

    by_order: dict[int, dict[str, Any]] = {}
    for c in payload.get("chunks") or []:
        if isinstance(c, dict) and isinstance(c.get("order"), int):
            by_order[int(c["order"])] = c

    child_orders = list(parent.get("child_orders") or [])
    if not child_orders:
        kids = [
            c
            for c in (payload.get("chunks") or [])
            if isinstance(c, dict) and str(c.get("parent_id") or "") == pid
        ]
        kids.sort(key=lambda r: int(r.get("order") or 0))
        texts = [str(k.get("text") or "") for k in kids]
        child_orders = [int(k["order"]) for k in kids if isinstance(k.get("order"), int)]
    else:
        texts = [
            str((by_order.get(o) or {}).get("text") or "")
            for o in child_orders
            if isinstance(o, int)
        ]

    full = join_texts_dedupe_overlap(texts)
    parent["content"] = full
    parent["token_len"] = max(1, len(full) // 2) if full else 0
    if child_orders and not parent.get("child_orders"):
        parent["child_orders"] = child_orders
        parent["child_count"] = len(child_orders)
    return True


def patch_sidecar_chunk_text(
    doc_id: str,
    *,
    order: int | None,
    text: str,
) -> bool:
    """按 order 回写侧车中该片正文；若属拆章子片则同步重算父章全文。"""
    payload = load_chunk_sidecar(doc_id)
    if not payload or not isinstance(order, int):
        return False
    changed = False
    parent_id: str | None = None
    for row in payload.get("chunks") or []:
        if isinstance(row, dict) and row.get("order") == order:
            row["text"] = text
            row["token_len"] = max(1, len(text or "") // 2) if text else 0
            pid = row.get("parent_id")
            parent_id = str(pid) if pid else None
            changed = True
            break
    if not changed:
        return False
    if parent_id:
        rebuild_parent_content(payload, parent_id)
    save_chunk_sidecar(doc_id, payload)
    return True
