"""文档切分管线。

主入口：
- ``split_file``：按后缀切出 ``Chunk`` 列表（含 Plan A/B + 尺寸治理）
- ``split_file_to_rag_chunks``：产出可交给 ``adapt_rag_chunks_to_lightrag`` 的片
"""

from app.rag.splitter.adapt import (
    chunks_to_rag_chunks,
    split_file_to_rag_chunks,
)
from app.rag.splitter.router import split_file

__all__ = [
    "split_file",
    "split_file_to_rag_chunks",
    "chunks_to_rag_chunks",
]
