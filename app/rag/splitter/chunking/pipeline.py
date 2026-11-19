"""blocks → Chunk 唯一入口（标题试切 → 路径 A/B → 输出）。"""

from __future__ import annotations

from typing import Any

from app.rag.splitter.chunking.path_b import path_b_split_fulltext
from app.rag.splitter.chunking.route import decide_route, trial_full_text
from app.rag.splitter.chunking.size_govern import govern_chunks
from app.rag.splitter.chunking.title_tree import merge_title_only_sections, split_units_by_title
from app.rag.splitter.chunking.units import blocks_to_units
from app.rag.splitter.models import Chunk


def _sections_to_trial_chunks(
    sections: list[Any],
    *,
    source: str = "",
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for order, sec in enumerate(sections):
        text = sec.text
        if not text:
            continue
        title_path = list(sec.title_path)
        section_title = sec.section_title
        if sec.chunk_type == "toc" and not section_title:
            section_title = "目录"
        meta: dict[str, Any] = {
            "section_title": section_title,
        }
        if source:
            meta["source"] = source
        chunks.append(
            Chunk(
                chunk_id=f"sec_{order}",
                order=order,
                text=text,
                page=sec.page,
                title_path=title_path,
                chunk_type=sec.chunk_type or "text",
                meta=meta,
            )
        )
    return chunks


def blocks_to_chunks(
    blocks: list[dict[str, Any]],
    *,
    source: str = "",
) -> list[Chunk]:
    """标题树试切 → 判定 A/B → 路径 A 尺寸治理 或 路径 B 全文窗切。"""
    units = blocks_to_units(blocks)
    sections = split_units_by_title(units)
    sections = merge_title_only_sections(sections)
    trial = _sections_to_trial_chunks(sections, source=source)

    decision = decide_route(trial, blocks=blocks)

    if decision.route == "B":
        full_text = trial_full_text(trial)
        chunks = path_b_split_fulltext(full_text, source=source)
        return chunks

    # 路径 A：过短合 + 过长节二次切
    governed, _parents = govern_chunks(trial)
    for c in governed:
        if isinstance(c.meta, dict):
            c.meta.setdefault("route", "A")
    return governed
