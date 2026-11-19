"""Short-chunk merge ported from rag-project (merge_short_chunks only).

Kept free of embedding / Flask / app.config imports so it can ship as a
library inside LightRAG.
"""

from __future__ import annotations

from statistics import median
from typing import Any

import tiktoken

_ENC = None


def calc_token_len(text: str) -> int:
    """Token length via tiktoken ``cl100k_base`` (same as rag-project)."""
    global _ENC
    if _ENC is None:
        _ENC = tiktoken.get_encoding("cl100k_base")
    return len(_ENC.encode(text or ""))


def calculate_pre_validation_metrics(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute per-chunk content token lengths used by :func:`merge_short_chunks`."""
    chunk_token_lengths: list[int] = []
    chunk_details: list[dict[str, Any]] = []
    for chunk_item in chunks:
        text = chunk_item.get("text", "") or ""
        title_path = chunk_item.get("title_path") or []
        total_tokens = calc_token_len(text)
        chunk_token_lengths.append(total_tokens)

        title_len_tokens = 0
        if title_path:
            for title in title_path:
                title_clean = str(title).strip()
                if not title_clean:
                    continue
                title_no_newline = title_clean.replace("\n", "")
                if title_no_newline in text:
                    title_len_tokens += calc_token_len(title_no_newline)
            content_len_tokens = total_tokens - title_len_tokens
        else:
            content_len_tokens = total_tokens

        chunk_details.append(
            {
                "chunk_id": chunk_item.get("chunk_id", ""),
                "total_tokens": total_tokens,
                "title_len": title_len_tokens,
                "content_len": content_len_tokens,
                "title_proportion": (
                    title_len_tokens / total_tokens if total_tokens > 0 else 0.0
                ),
            }
        )

    doc_total_tokens = sum(chunk_token_lengths)
    return {
        "doc_total_tokens": doc_total_tokens,
        "chunk_count": len(chunks),
        "median_chunk_tokens": (
            float(median(chunk_token_lengths)) if chunk_token_lengths else 0.0
        ),
        "doc_is_short": doc_total_tokens < 3000,
        "doc_is_long": doc_total_tokens > 20000,
        "chunk_details": chunk_details,
    }


def merge_short_chunks(
    chunks: list[dict[str, Any]], min_content_tokens: int = 20
) -> list[dict[str, Any]]:
    """Merge chunks whose body token count is at or below ``min_content_tokens``."""
    if not chunks:
        return chunks

    metrics = calculate_pre_validation_metrics(chunks)
    chunk_details = metrics.get("chunk_details", [])

    short_indices = [
        idx
        for idx, detail in enumerate(chunk_details)
        if detail.get("content_len", 0) <= min_content_tokens
    ]
    if not short_indices:
        return chunks

    merged_chunks: list[dict[str, Any]] = []
    skip_indices: set[int] = set()
    n = len(chunks)

    for idx in range(n):
        if idx in skip_indices:
            continue

        chunk = chunks[idx]
        content_len = chunk_details[idx].get("content_len", 0)

        if content_len <= min_content_tokens:
            if idx == n - 1:
                if idx > 0 and merged_chunks:
                    prev_chunk = merged_chunks[-1]
                    merged_text = (
                        (prev_chunk.get("text", "") or "")
                        + "\n"
                        + (chunk.get("text", "") or "")
                    )
                    prev_chunk["text"] = merged_text
                    prev_chunk["length"] = len(merged_text)
                    skip_indices.add(idx)
                else:
                    merged_chunks.append(chunk)
            else:
                next_idx = idx + 1
                while next_idx in skip_indices and next_idx < n - 1:
                    next_idx += 1

                if next_idx < n:
                    next_chunk = chunks[next_idx]
                    merged_text = (
                        (chunk.get("text", "") or "")
                        + "\n"
                        + (next_chunk.get("text", "") or "")
                    )
                    merged_chunks.append(
                        {
                            "chunk_id": next_chunk.get("chunk_id", ""),
                            "order": next_chunk.get("order", idx),
                            "doc_id": next_chunk.get("doc_id", ""),
                            "title": next_chunk.get("title", ""),
                            "title_path": next_chunk.get("title_path", []),
                            "text": merged_text,
                            "page": chunk.get("page", next_chunk.get("page", "")),
                            "type": next_chunk.get("type", "text"),
                            "length": len(merged_text),
                            "keywords": next_chunk.get("keywords", []),
                        }
                    )
                    skip_indices.add(idx)
                    skip_indices.add(next_idx)
                else:
                    merged_chunks.append(chunk)
        else:
            merged_chunks.append(chunk)

    for new_idx, chunk in enumerate(merged_chunks):
        chunk["order"] = new_idx + 1
        doc_id = chunk.get("doc_id", "")
        chunk["chunk_id"] = f"{doc_id}_{new_idx + 1}"

    return merged_chunks
