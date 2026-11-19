"""文档切分抽象基类。各格式实现放在 pdf/ / word/ / ppt/ 下。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.rag.splitter.models import Chunk


class DocumentSplitter(ABC):
    """拿到本地文件路径后，解析并产出有序分片列表。"""

    #: 本实现声明支持的后缀（小写，含点），供路由校验
    supported_suffixes: tuple[str, ...] = ()

    @abstractmethod
    def split(self, file_path: Path) -> list[Chunk]:
        """解析 ``file_path``，返回按文档顺序排列的分片。"""

    def ensure_supported(self, file_path: Path) -> None:
        suffix = file_path.suffix.lower()
        if self.supported_suffixes and suffix not in self.supported_suffixes:
            raise ValueError(
                f"{self.__class__.__name__} 不支持后缀 {suffix!r}，"
                f"仅支持 {self.supported_suffixes}"
            )

    def run(self, file_path: str | Path) -> list[Chunk]:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {path}")
        self.ensure_supported(path)
        return self.split(path)
