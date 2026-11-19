"""按后缀把文件转发到 pdf / word / ppt 实现。"""

from __future__ import annotations

from pathlib import Path

from app.rag.splitter.base import DocumentSplitter
from app.rag.splitter.models import Chunk
from app.rag.splitter.pdf.splitter import PdfSplitter
from app.rag.splitter.ppt.splitter import PptSplitter
from app.rag.splitter.word.splitter import WordSplitter

# 后缀 → 切分器（可在此扩展 .doc / .ppt 等）
_ROUTES: dict[str, type[DocumentSplitter]] = {
    ".pdf": PdfSplitter,
    ".docx": WordSplitter,
    ".doc": WordSplitter,
    ".pptx": PptSplitter,
    ".ppt": PptSplitter,
}


def get_splitter(file_path: str | Path) -> DocumentSplitter:
    path = Path(file_path)
    suffix = path.suffix.lower()
    cls = _ROUTES.get(suffix)
    if cls is None:
        supported = ", ".join(sorted(_ROUTES))
        raise ValueError(f"不支持的文件类型 {suffix!r}，当前支持: {supported}")
    return cls()


def split_file(file_path: str | Path) -> list[Chunk]:
    """统一入口：选实现 → 切分。"""
    return get_splitter(file_path).run(file_path)
