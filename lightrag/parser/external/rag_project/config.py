"""Ingest-backend selection for the rag-project facade vs LightRAG native path.

``LIGHTRAG_INGEST_BACKEND``:

- ``rag_project`` (default): PDF/Word go through the migrated rag-project
  read → split → ``merge_short_chunks`` facade; other suffixes are rejected.
- ``lightrag``: existing parse engines + F/R/V/P chunking unchanged.
"""

from __future__ import annotations

from lightrag.utils import get_env_value

INGEST_BACKEND_RAG_PROJECT = "rag_project"
INGEST_BACKEND_LIGHTRAG = "lightrag"
_VALID_BACKENDS = frozenset(
    {INGEST_BACKEND_RAG_PROJECT, INGEST_BACKEND_LIGHTRAG}
)

# Filename suffixes accepted by the rag-project facade (leading dot).
# ``.doc`` / ``.ppt`` 由业务侧入库前转为 ``.docx`` / ``.pptx``；
# PPT 仅在 ``MDM_RAG_SPLITTER=split_v2`` 下可完整解析。
RAG_PROJECT_SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".pptx", ".ppt"})


def get_ingest_backend() -> str:
    """Return the active ingest backend (lower-cased, validated)."""
    raw = str(
        get_env_value(
            "LIGHTRAG_INGEST_BACKEND",
            INGEST_BACKEND_RAG_PROJECT,
            str,
        )
        or INGEST_BACKEND_RAG_PROJECT
    ).strip().lower()
    if raw not in _VALID_BACKENDS:
        return INGEST_BACKEND_RAG_PROJECT
    return raw


def is_rag_project_ingest() -> bool:
    return get_ingest_backend() == INGEST_BACKEND_RAG_PROJECT


def is_rag_project_supported_path(file_path: str) -> bool:
    """True when ``file_path`` has a PDF/Word/PPT suffix the facade can ingest."""
    name = (file_path or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    # Strip LightRAG filename hints like ``report.[mineru].pdf`` → ``.pdf``.
    lower = name.lower()
    for suffix in RAG_PROJECT_SUPPORTED_SUFFIXES:
        if lower.endswith(suffix):
            return True
    # Hint form: stem.[engine-options].ext
    if "]." in lower:
        after = lower.rsplit("].", 1)[-1]
        return f".{after}" in RAG_PROJECT_SUPPORTED_SUFFIXES
    return False


def unsupported_ingest_message(file_path: str) -> str:
    return (
        f"当前 ingest 后端为 rag_project，支持 PDF / Word / PPT"
        f"（.pdf .docx .pptx；.doc/.ppt 需先转换）；"
        f"不支持: {file_path or '<unknown>'}。"
        f"如需使用其它格式，请将 LIGHTRAG_INGEST_BACKEND 设为 lightrag。"
    )
