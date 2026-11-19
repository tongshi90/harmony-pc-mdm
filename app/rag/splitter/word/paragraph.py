"""Word 段落 → 带样式/字号/加粗的 text line。"""

from __future__ import annotations

import re
from typing import Any

_HEADING_RE = re.compile(
    r"^(heading|标题)\s*(\d+)$",
    re.IGNORECASE,
)


def style_name_of(paragraph: Any) -> str:
    try:
        if paragraph.style and getattr(paragraph.style, "name", None):
            return str(paragraph.style.name)
    except (AttributeError, TypeError):
        pass
    return ""


def is_heading_style(style_name: str) -> bool:
    name = (style_name or "").strip()
    if not name:
        return False
    if _HEADING_RE.match(name):
        return True
    lower = name.lower()
    return lower.startswith("heading") or name.startswith("标题") or "标题" in name


def heading_level_from_style(style_name: str, paragraph: Any = None) -> int:
    """样式层级：优先 outlineLvl，其次样式名中的数字。"""
    if paragraph is not None:
        try:
            pPr = paragraph._p.pPr
            if pPr is not None and pPr.outlineLvl is not None:
                # Word outlineLvl 0-based
                return max(int(pPr.outlineLvl.val) + 1, 1)
        except Exception:
            pass
    m = _HEADING_RE.match((style_name or "").strip())
    if m:
        return max(int(m.group(2)), 1)
    digits = "".join(c for c in (style_name or "") if c.isdigit())
    if digits:
        return max(int(digits), 1)
    return 1


def _pt_from_length(length: Any) -> float | None:
    if length is None:
        return None
    try:
        return float(length.pt)
    except Exception:
        return None


def measure_runs(paragraph: Any) -> tuple[float | None, float, bool]:
    """返回 (主导字号pt, 加粗字符占比, 是否整段可视为加粗)。"""
    runs = list(paragraph.runs or [])
    if not runs:
        # 无 run 时尝试样式字号
        size = None
        try:
            size = _pt_from_length(paragraph.style.font.size) if paragraph.style else None
        except Exception:
            size = None
        return size, 0.0, False

    total_chars = 0
    bold_chars = 0
    size_weights: dict[float, int] = {}

    for run in runs:
        text = run.text or ""
        n = max(len(text), 1) if text else 0
        if not text:
            continue
        total_chars += len(text)
        is_bold = False
        try:
            if run.bold is True:
                is_bold = True
            elif run.bold is None and run.font and run.font.bold is True:
                is_bold = True
        except Exception:
            pass
        if is_bold:
            bold_chars += len(text)

        size = None
        try:
            size = _pt_from_length(run.font.size)
        except Exception:
            size = None
        if size is None:
            try:
                size = _pt_from_length(paragraph.style.font.size) if paragraph.style else None
            except Exception:
                size = None
        if size is not None:
            rs = round(float(size) * 2) / 2.0
            size_weights[rs] = size_weights.get(rs, 0) + len(text)

    body_size = None
    if size_weights:
        body_size = max(size_weights.items(), key=lambda kv: kv[1])[0]
    bold_ratio = (bold_chars / total_chars) if total_chars else 0.0
    is_full_bold = bold_ratio >= 0.98 and total_chars > 0
    return body_size, bold_ratio, is_full_bold


def paragraph_to_line(paragraph: Any) -> dict[str, Any] | None:
    """将段落转为与 PDF 同构的 line dict；空段落返回 None。"""
    text = (paragraph.text or "").strip()
    if not text:
        return None
    style = style_name_of(paragraph)
    size, bold_ratio, is_full_bold = measure_runs(paragraph)
    line: dict[str, Any] = {
        "text": text,
        "size": size,
        "bold_ratio": bold_ratio,
        "is_full_bold": is_full_bold,
        "style_name": style,
        "is_heading_style": is_heading_style(style),
        "style_level": heading_level_from_style(style, paragraph)
        if is_heading_style(style)
        else None,
        "role": "body",
        "level": None,
        "title_via": None,
        # 无页坐标；占位便于复用部分逻辑
        "bbox": None,
    }
    return line
