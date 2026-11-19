"""Migrated rag-project document ingest (read → split → merge_short_chunks).

Selected via ``LIGHTRAG_INGEST_BACKEND=rag_project`` (default). Set
``LIGHTRAG_INGEST_BACKEND=lightrag`` to restore the built-in parse + F/R/V/P
pipeline unchanged.
"""

from lightrag.parser.external.rag_project.config import (
    INGEST_BACKEND_LIGHTRAG,
    INGEST_BACKEND_RAG_PROJECT,
    get_ingest_backend,
    is_rag_project_ingest,
    is_rag_project_supported_path,
    unsupported_ingest_message,
)
from lightrag.parser.external.rag_project.ingest import (
    PARSER_ENGINE_RAG_PROJECT,
    RagIngestResult,
    adapt_rag_chunks_to_lightrag,
    ingest_file,
)

__all__ = [
    "INGEST_BACKEND_LIGHTRAG",
    "INGEST_BACKEND_RAG_PROJECT",
    "PARSER_ENGINE_RAG_PROJECT",
    "RagIngestResult",
    "adapt_rag_chunks_to_lightrag",
    "get_ingest_backend",
    "ingest_file",
    "is_rag_project_ingest",
    "is_rag_project_supported_path",
    "unsupported_ingest_message",
]
