"""路径 B：丢弃标题边界，全文按长度/段落窗切。"""

from __future__ import annotations

from typing import Any

from app.rag.splitter.chunking import size_govern as sg
from app.rag.splitter.chunking.size_govern import (
    CHUNK_OVERLAP_RATIO,
    CHUNK_TOKEN_TARGET,
    MAX_CHUNK_TOKENS,
    estimate_tokens,
    split_text_to_windows,
)
from app.rag.splitter.models import Chunk


def path_b_split_fulltext(
    full_text: str,
    *,
    source: str = "",
) -> list[Chunk]:
    """整篇 plain 窗切；无 title_path / parent_id，写 prev/next。"""
    # 路径 B 无父块
    sg._LAST_PARENTS = []

    text = (full_text or "").strip()
    if not text:
        return []

    windows = split_text_to_windows(
        text,
        target=CHUNK_TOKEN_TARGET,
        max_tokens=MAX_CHUNK_TOKENS,
        overlap_ratio=CHUNK_OVERLAP_RATIO,
    )
    if not windows:
        windows = [text]

    chunks: list[Chunk] = []
    for i, w in enumerate(windows):
        meta: dict[str, Any] = {
            "section_title": "",
            "doc_type": "plain",
            "parent_id": None,
            "route": "B",
            "token_len": estimate_tokens(w),
        }
        if source:
            meta["source"] = source
        chunks.append(
            Chunk(
                chunk_id=f"plain_{i}",
                order=i,
                text=w,
                page=None,
                title_path=[],
                chunk_type="text",
                meta=meta,
            )
        )

    return sg._reindex_and_link(chunks)
