"""切分结果的通用数据结构（仅本目录使用，不依赖项目其它包）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Chunk:
    """单个分片。后续合并回业务时可按需对齐 LightRAG 字段。"""

    chunk_id: str
    order: int
    text: str
    # page / slide 等；Word 可固定 1 或留空
    page: int | None = None
    # 标题路径，如 ["第一章", "第一节"]
    title_path: list[str] = field(default_factory=list)
    # text | table | image | slide | ...
    chunk_type: str = "text"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
