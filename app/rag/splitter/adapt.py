"""Chunk → rag_project 原始片形态，供 adapt_rag_chunks_to_lightrag 复用。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.rag.splitter.chunking import get_last_parents, get_last_route_decision
from app.rag.splitter.models import Chunk
from app.rag.splitter.router import split_file


def chunks_to_rag_chunks(
    chunks: list[Chunk],
    *,
    doc_id: str,
) -> list[dict[str, Any]]:
    """把 splitter ``Chunk`` 转成 rag_project 风格 dict。

    ``type=toc`` 会在后续 ``adapt_rag_chunks_to_lightrag`` 中丢弃（与 catalog 一致）。
    """
    out: list[dict[str, Any]] = []
    for c in chunks:
        ctype = str(c.chunk_type or "text").lower()
        # 对齐旧 ingest：目录片用 catalog，便于 adapt 统一丢弃
        if ctype == "toc":
            ctype = "catalog"
        meta = dict(c.meta) if isinstance(c.meta, dict) else {}
        row: dict[str, Any] = {
            "chunk_id": c.chunk_id,
            "order": int(c.order),
            "doc_id": doc_id,
            "title_path": list(c.title_path or []),
            "text": c.text or "",
            "page": c.page,
            "type": ctype,
            "length": len(c.text or ""),
            "keywords": [],
            "meta": {
                "doc_type": meta.get("doc_type"),
                "parent_id": meta.get("parent_id"),
                "prev_id": meta.get("prev_id"),
                "next_id": meta.get("next_id"),
                "route": meta.get("route"),
                "token_len": meta.get("token_len"),
                "section_title": meta.get("section_title"),
                "source": meta.get("source"),
            },
        }
        out.append(row)
    return out


def build_sidecar_payload(
    rag_chunks: list[dict[str, Any]],
    *,
    doc_id: str,
    source_path: str | None = None,
) -> dict[str, Any]:
    """构建侧车：仅保留会被向量化的片（排除 catalog/toc），order 与 LightRAG 对齐。"""
    parents = get_last_parents()
    decision = get_last_route_decision()
    route = None
    route_detail = None
    if decision is not None:
        route = decision.route
        route_detail = decision.to_dict()

    embeddable: list[dict[str, Any]] = []
    order = 0
    # splitter_id → final order（用于重写 prev/next/parent child 引用）
    id_to_order: dict[str, int] = {}
    for raw in rag_chunks:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("type") or "").lower() in {"catalog", "toc"}:
            continue
        text = str(raw.get("text") or "").strip()
        if not text and not (raw.get("title_path") or []):
            continue
        sid = str(raw.get("chunk_id") or f"sec_{order}")
        id_to_order[sid] = order
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        embeddable.append(
            {
                "order": order,
                "splitter_chunk_id": sid,
                "text": str(raw.get("text") or ""),
                "title_path": list(raw.get("title_path") or []),
                "doc_type": meta.get("doc_type"),
                "parent_id": meta.get("parent_id"),
                "prev_id": meta.get("prev_id"),
                "next_id": meta.get("next_id"),
                "route": meta.get("route") or route,
                "token_len": meta.get("token_len"),
                "section_title": meta.get("section_title"),
                "page": raw.get("page"),
                "parent_child_index": None,
                "parent_child_count": None,
            }
        )
        order += 1

    # prev/next 改为最终 order 索引，便于提问侧按邻域扩窗
    by_sid = {r["splitter_chunk_id"]: r for r in embeddable}
    for row in embeddable:
        prev_sid = row.get("prev_id")
        next_sid = row.get("next_id")
        row["prev_order"] = id_to_order.get(str(prev_sid)) if prev_sid else None
        row["next_order"] = id_to_order.get(str(next_sid)) if next_sid else None

    # 同父章节下的子片序号（过长章二次切）
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in embeddable:
        pid = row.get("parent_id")
        if pid:
            children_by_parent.setdefault(str(pid), []).append(row)
    for kids in children_by_parent.values():
        kids.sort(key=lambda r: int(r.get("order") or 0))
        total = len(kids)
        for i, kid in enumerate(kids):
            kid["parent_child_index"] = i
            kid["parent_child_count"] = total

    parent_rows: list[dict[str, Any]] = []
    for p in parents or []:
        if not isinstance(p, dict):
            continue
        child_ids = [str(x) for x in (p.get("child_ids") or []) if x]
        child_orders = [id_to_order[c] for c in child_ids if c in id_to_order]
        parent_rows.append(
            {
                "parent_id": p.get("parent_id"),
                "content": p.get("content") or "",
                "title_path": list(p.get("title_path") or []),
                "section_title": p.get("section_title") or "",
                "token_len": p.get("token_len"),
                "child_ids": child_ids,
                "child_orders": child_orders,
                "child_count": len(child_orders),
            }
        )

    return {
        "doc_id": doc_id,
        "source": source_path,
        "splitter": "split_v2",
        "route": route,
        "route_detail": route_detail,
        "chunk_count": len(embeddable),
        "chunks": embeddable,
        "parents": parent_rows,
        # 便于调试；不参与向量
        "_by_sid_count": len(by_sid),
    }


def split_file_to_rag_chunks(
    path: str | Path,
    *,
    doc_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """切分文件并产出 rag 片 + 侧车 payload。"""
    p = Path(path)
    chunks = split_file(p)
    rag_chunks = chunks_to_rag_chunks(chunks, doc_id=doc_id)
    sidecar = build_sidecar_payload(
        rag_chunks, doc_id=doc_id, source_path=str(p)
    )
    return rag_chunks, sidecar


# 写入 LightRAG text_chunks / chunks_vdb 的关联字段（不含父章全文，全文仍在侧车）
CHUNK_RELATION_FIELDS = (
    "chunk_order_index",
    "doc_chunk_count",
    "doc_type",
    "title_path",
    "section_title",
    "parent_id",
    "parent_child_index",
    "parent_child_count",
    "prev_order",
    "next_order",
    "route",
)


def enrich_lightrag_chunks_with_relations(
    lightrag_chunks: list[dict[str, Any]],
    *,
    sidecar: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """把文档顺序 / 父章节 / 子片序号等关联信息挂到待向量化的 chunk 上。

    - ``text_chunks`` 会完整保留这些字段（``build_chunks_dict_from_chunking_result``）
    - ``chunks_vdb`` 需在引擎侧把同名字段加入 ``meta_fields`` 才会进向量元数据
    - 父章全文不写进向量片（体积大），仍在 sidecar.parents
    """
    if not lightrag_chunks:
        return []

    total = len(lightrag_chunks)
    by_order: dict[int, dict[str, Any]] = {}
    if isinstance(sidecar, dict):
        for row in sidecar.get("chunks") or []:
            if isinstance(row, dict) and isinstance(row.get("order"), int):
                by_order[int(row["order"])] = row

    out: list[dict[str, Any]] = []
    for i, raw in enumerate(lightrag_chunks):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        order = item.get("chunk_order_index")
        if not isinstance(order, int):
            order = i
            item["chunk_order_index"] = order

        side = by_order.get(order) or {}
        title_path = side.get("title_path")
        if not isinstance(title_path, list):
            # 回退：从 heading 拼
            heading = item.get("heading") if isinstance(item.get("heading"), dict) else {}
            parents = list(heading.get("parent_headings") or [])
            leaf = heading.get("heading")
            title_path = [str(p) for p in parents if p] + (
                [str(leaf)] if leaf else []
            )

        item["doc_chunk_count"] = total
        item["doc_type"] = side.get("doc_type") or (
            "rule" if title_path else "plain"
        )
        item["title_path"] = list(title_path or [])
        item["section_title"] = side.get("section_title") or (
            title_path[-1] if title_path else ""
        )
        item["parent_id"] = side.get("parent_id")
        item["parent_child_index"] = side.get("parent_child_index")
        item["parent_child_count"] = side.get("parent_child_count")
        item["prev_order"] = (
            side.get("prev_order") if "prev_order" in side else (order - 1 if order > 0 else None)
        )
        item["next_order"] = (
            side.get("next_order")
            if "next_order" in side
            else (order + 1 if order + 1 < total else None)
        )
        item["route"] = side.get("route")
        out.append(item)
    return out
