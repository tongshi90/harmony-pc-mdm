"""LightRAG chunking strategies (MDM vendored subset).

Keeps fixed/legacy token chunkers and ``recursive_character`` (needed by
addon_params separator normalization at LightRAG init). Semantic / paragraph
(V/P) strategies were removed as unused by the MDM ``rag_project`` path.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from lightrag.chunker.registry import (
    ChunkingContext,
    accepts_chunking_context,
    callback_supports_context,
    invoke_chunker,
)

if TYPE_CHECKING:
    from lightrag.chunker.recursive_character import chunking_by_recursive_character
    from lightrag.chunker.token_size import (
        chunking_by_fixed_token,
        chunking_by_token_size,
    )

_EXPORT_MODULES = {
    "chunking_by_fixed_token": "token_size",
    "chunking_by_token_size": "token_size",
    "chunking_by_recursive_character": "recursive_character",
}


def __getattr__(name: str) -> Any:
    module = _EXPORT_MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"lightrag.chunker.{module}"), name)
    globals()[name] = value
    return value


__all__ = [
    "ChunkingContext",
    "accepts_chunking_context",
    "callback_supports_context",
    "chunking_by_fixed_token",
    "chunking_by_recursive_character",
    "chunking_by_token_size",
    "invoke_chunker",
]
