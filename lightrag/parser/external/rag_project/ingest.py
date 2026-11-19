"""Facade: rag-project file read → split → merge_short_chunks → LightRAG chunks.

Used when ``LIGHTRAG_INGEST_BACKEND=rag_project`` (default). Produces:

- ``content``: full-document text for ``full_docs`` / dedup
- ``chunks``: LightRAG chunker-shaped dicts (``content`` / ``tokens`` /
  ``chunk_order_index`` / ``heading``), with ``title_path`` reflected in both
  ``content`` (breadcrumb prefix) and ``heading``
- catalog (``type=catalog``) chunks are dropped
- PDF images are extracted via ``img_splitter`` and appended as text chunks
  when OCR text (or a page placeholder) is available
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from lightrag.constants import FULL_DOCS_FORMAT_RAW
from lightrag.parser.external.rag_project.config import (
    RAG_PROJECT_SUPPORTED_SUFFIXES,
    is_rag_project_supported_path,
    unsupported_ingest_message,
)
from lightrag.parser.external.rag_project.merge_short_chunks import merge_short_chunks

logger = logging.getLogger(__name__)

PARSER_ENGINE_RAG_PROJECT = "rag_project"


class _Tokenizer(Protocol):
    def encode(self, text: str) -> list[int]: ...


@dataclass
class RagIngestResult:
    content: str
    chunks: list[dict[str, Any]]
    parse_format: str = FULL_DOCS_FORMAT_RAW
    parse_engine: str = PARSER_ENGINE_RAG_PROJECT
    meta: dict[str, Any] = field(default_factory=dict)


def _suffix(path: Path) -> str:
    return path.suffix.lower()


def _is_word(path: Path) -> bool:
    return _suffix(path) == ".docx"


def _breadcrumb(title_path: list[str] | None) -> str:
    parts = [str(p).strip() for p in (title_path or []) if str(p).strip()]
    return " > ".join(parts)


def _heading_from_title_path(title_path: list[str] | None) -> dict[str, Any] | None:
    parts = [str(p).strip() for p in (title_path or []) if str(p).strip()]
    if not parts:
        return None
    return {
        "level": len(parts),
        "heading": parts[-1],
        "parent_headings": parts[:-1],
    }


def _compose_content(title_path: list[str] | None, text: str) -> str:
    body = (text or "").strip()
    crumb = _breadcrumb(title_path)
    if crumb and body:
        # Avoid duplicating when the body already starts with the leaf title.
        leaf = title_path[-1].strip() if title_path else ""
        if leaf and body.startswith(leaf):
            return f"{crumb}\n\n{body}" if not body.startswith(crumb) else body
        return f"{crumb}\n\n{body}"
    return crumb or body


def adapt_rag_chunks_to_lightrag(
    rag_chunks: list[dict[str, Any]],
    *,
    tokenizer: _Tokenizer,
) -> list[dict[str, Any]]:
    """Map rag-project chunks → LightRAG chunker return shape.

    Drops ``type == catalog|toc``. Writes ``title_path`` into both ``content``
    (breadcrumb) and ``heading``. Preserves splitter ``chunk_id`` when present
    so LightRAG can form stable ``{doc_id}-{chunk_id}`` keys.
    """
    out: list[dict[str, Any]] = []
    order = 0
    for raw in rag_chunks:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("type") or "").lower() in {"catalog", "toc"}:
            continue
        title_path = raw.get("title_path") or []
        if not isinstance(title_path, list):
            title_path = []
        content = _compose_content(title_path, str(raw.get("text") or ""))
        if not content.strip():
            continue
        tokens = len(tokenizer.encode(content))
        item: dict[str, Any] = {
            "content": content,
            "tokens": tokens,
            "chunk_order_index": order,
        }
        raw_cid = str(raw.get("chunk_id") or "").strip()
        if raw_cid:
            item["chunk_id"] = raw_cid
        heading = _heading_from_title_path(title_path)
        if heading is not None:
            item["heading"] = heading
        out.append(item)
        order += 1
    return out


def _image_chunks_as_rag_text(
    pdf_path: str, doc_id: str
) -> list[dict[str, Any]]:
    """Extract PDF images and turn them into rag-shaped text chunks."""
    try:
        from lightrag.parser.external.rag_project.img_splitter import (
            split_images_from_pdf,
        )
    except Exception as exc:  # pragma: no cover - import/env issues
        logger.warning("[rag_project] img_splitter unavailable: %s", exc)
        return []

    try:
        images = split_images_from_pdf(pdf_path, ocr_model=None)
    except ImportError as exc:
        logger.warning(
            "[rag_project] PDF image extraction skipped (missing dependency): %s",
            exc,
        )
        return []
    except Exception as exc:
        logger.warning(
            "[rag_project] PDF image extraction failed for %s: %s", pdf_path, exc
        )
        return []

    out: list[dict[str, Any]] = []
    for idx, img in enumerate(images):
        page = img.get("page") or 0
        ocr = (img.get("content") or "").strip()
        # Without OCR, still keep a locatable placeholder so the image is not
        # silently dropped from the knowledge surface.
        if ocr:
            text = f"[Image page={page}]\n{ocr}"
        else:
            info = img.get("image_info") or {}
            w, h = info.get("width", 0), info.get("height", 0)
            text = f"[Image page={page} size={w}x{h}]"
        title_path = [f"图片 (第{page}页)"]
        out.append(
            {
                "chunk_id": f"{doc_id}_img_{idx + 1}",
                "order": 0,  # reassigned after merge
                "doc_id": doc_id,
                "title_path": title_path,
                "text": text,
                "page": page,
                "type": "text",
                "length": len(text),
                "keywords": [],
            }
        )
    return out


def _split_document(path: Path, doc_id: str) -> tuple[list[dict[str, Any]], dict]:
    if _is_word(path):
        from lightrag.parser.external.rag_project.word_splitter import (
            split_word_to_chunks,
        )

        return split_word_to_chunks(str(path), file_id=doc_id, kb_id=None)

    from lightrag.parser.external.rag_project.text_splitter import (
        split_pdf_to_chunks,
    )

    return split_pdf_to_chunks(str(path), file_id=doc_id, kb_id=None)


def _resolve_splitter_mode() -> str:
    """``MDM_RAG_SPLITTER``: ``split_v2``（新）或 ``rag_project``（旧 TitleDetector）。"""
    import os

    raw = (os.environ.get("MDM_RAG_SPLITTER") or "").strip().lower()
    if not raw:
        try:
            from app.config import settings

            raw = str(getattr(settings, "rag_splitter", "") or "").strip().lower()
        except Exception:
            raw = ""
    if raw in {"split_v2", "split", "v2"}:
        return "split_v2"
    return "rag_project"


def ingest_file(
    source_path: str | Path,
    *,
    doc_id: str,
    tokenizer: _Tokenizer,
    file_path_hint: str | None = None,
) -> RagIngestResult:
    """Run the full rag-project ingest pipeline for one on-disk file.

    Raises:
        ValueError: unsupported suffix (with a Chinese operator message).
        FileNotFoundError: source missing.
        Exception: propagated from underlying splitters.
    """
    path = Path(source_path)
    display = file_path_hint or path.name
    if not path.is_file():
        raise FileNotFoundError(f"rag_project source file not found: {path}")

    if not is_rag_project_supported_path(display) and _suffix(
        path
    ) not in RAG_PROJECT_SUPPORTED_SUFFIXES:
        raise ValueError(unsupported_ingest_message(display))

    if _suffix(path) not in RAG_PROJECT_SUPPORTED_SUFFIXES:
        raise ValueError(unsupported_ingest_message(display))

    splitter_mode = _resolve_splitter_mode()
    if splitter_mode != "split_v2" and _suffix(path) in {".ppt", ".pptx"}:
        raise ValueError(
            f"PPT 仅在 MDM_RAG_SPLITTER=split_v2 下支持解析："
            f"{display}（当前切分器={splitter_mode}）"
        )
    result_info: dict[str, Any] = {}
    sidecar_payload: dict[str, Any] | None = None

    if splitter_mode == "split_v2":
        from app.rag.splitter.adapt import split_file_to_rag_chunks

        rag_chunks, sidecar_payload = split_file_to_rag_chunks(path, doc_id=doc_id)
        result_info = {
            "splitter": "split_v2",
            "route": (sidecar_payload or {}).get("route"),
        }
        # split_v2 流内已含图文（VL）；不再 append rag_project 图片片，避免双通道重复
        logger.info(
            "[rag_project] splitter=split_v2 chunks=%d route=%s file=%s",
            len(rag_chunks),
            result_info.get("route"),
            display,
        )
    else:
        rag_chunks, result_info = _split_document(path, doc_id)
        if not isinstance(rag_chunks, list):
            rag_chunks = []

        if _suffix(path) == ".pdf":
            image_chunks = _image_chunks_as_rag_text(str(path), doc_id)
            if image_chunks:
                logger.info(
                    "[rag_project] appended %d image chunk(s) for %s",
                    len(image_chunks),
                    display,
                )
                rag_chunks = list(rag_chunks) + image_chunks

        rag_chunks = merge_short_chunks(rag_chunks, min_content_tokens=20)
        result_info = dict(result_info) if isinstance(result_info, dict) else {}
        result_info["splitter"] = "rag_project"

    lightrag_chunks = adapt_rag_chunks_to_lightrag(rag_chunks, tokenizer=tokenizer)

    # 关联元数据写入待向量化 chunk（顺序 / 父章节 / 子片序号 / 邻域）
    from app.rag.splitter.adapt import enrich_lightrag_chunks_with_relations

    lightrag_chunks = enrich_lightrag_chunks_with_relations(
        lightrag_chunks, sidecar=sidecar_payload
    )

    if splitter_mode == "split_v2" and sidecar_payload is not None:
        try:
            from app.rag.splitter.sidecar import save_chunk_sidecar

            save_chunk_sidecar(doc_id, sidecar_payload)
        except Exception:
            logger.exception(
                "[rag_project] failed to persist chunk sidecar doc=%s", doc_id
            )

    # Document body for full_docs: join adapted contents so dedup/hash see the
    # same surface that will be chunked/embedded.
    content = "\n\n".join(
        c["content"] for c in lightrag_chunks if c.get("content")
    ).strip()
    if not content:
        raise ValueError(
            f"rag_project extracted no usable text from {display} (doc_id={doc_id})"
        )

    return RagIngestResult(
        content=content,
        chunks=lightrag_chunks,
        meta={
            "rag_chunk_count": len(lightrag_chunks),
            "splitter": splitter_mode,
            "rag_result_info_keys": (
                list(result_info.keys()) if isinstance(result_info, dict) else []
            ),
            "route": result_info.get("route") if isinstance(result_info, dict) else None,
        },
    )
