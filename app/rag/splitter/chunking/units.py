"""将 annotated blocks 展平为有序 unit 流，供标题树切分使用。"""

from __future__ import annotations

from typing import Any


def blocks_to_units(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """展平为 unit 序列，保持阅读序。

    unit.kind:
      - line: 来自 text.lines（含 role/level/in_toc/page）
      - table: 表格整块
      - image: 图片整块（文本为 VL 转写）
    """
    units: list[dict[str, Any]] = []
    for block in blocks:
        kind = block.get("kind")
        if kind == "text":
            for line in block.get("lines") or []:
                text = (line.get("text") or "").strip()
                if not text and (line.get("role") or "") != "title":
                    continue
                units.append(
                    {
                        "kind": "line",
                        "text": line.get("text") or "",
                        "role": line.get("role") or "body",
                        "level": line.get("level"),
                        "in_toc": bool(line.get("in_toc")),
                        "page": line.get("page")
                        if line.get("page") is not None
                        else block.get("page"),
                        "title_via": line.get("title_via"),
                    }
                )
        elif kind == "table":
            units.append(
                {
                    "kind": "table",
                    "text": block.get("text") or "",
                    "page": block.get("page"),
                }
            )
        elif kind == "image":
            units.append(
                {
                    "kind": "image",
                    "text": block.get("text") or "",
                    "page": block.get("page"),
                }
            )
    return units
