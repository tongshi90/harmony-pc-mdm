"""抽取文本清洗：去掉 Word/Wingdings 项目符号等私有区杂讯。"""

from __future__ import annotations

import re
from typing import Any

# Unicode 私有区（BMP）：Wingdings 子弹等常落在此
_PUA_RE = re.compile(r"[\uE000-\uF8FF]")

# 常见可见子弹（若已被映射成普通符号）
_BULLET_CHARS = (
    "\u2022"  # •
    "\u25CF"  # ●
    "\u25A0"  # ■
    "\u25AA"  # ▪
    "\u25E6"  # ◦
    "\u00B7"  # ·
    ""  # 常见乱码形态的 wingdings 点
)

_BULLET_RE = re.compile("[" + re.escape(_BULLET_CHARS) + "]")

# 字体名含这些则整字视为装饰符号，抽取阶段可直接丢弃
_DECORATIVE_FONT_RE = re.compile(
    r"(wingdings|symbol|webdings|dingbat|segoui\s*symbol)",
    re.IGNORECASE,
)


def is_decorative_font(fontname: str | None) -> bool:
    return bool(_DECORATIVE_FONT_RE.search(fontname or ""))


def is_decorative_char(text: str, fontname: str | None = None) -> bool:
    """单字是否为项目符号/装饰字符（可在 chars 阶段过滤）。"""
    if not text or text.isspace():
        return False
    if is_decorative_font(fontname):
        return True
    # 私有区单字符
    if len(text) == 1 and _PUA_RE.match(text):
        return True
    if len(text) == 1 and text in _BULLET_CHARS:
        return True
    return False


def clean_extracted_text(value: Any) -> str:
    """清洗单元格/段落文本：去 PUA、子弹，压缩空白。"""
    if value is None:
        return ""
    s = str(value)
    s = _PUA_RE.sub("", s)
    s = _BULLET_RE.sub("", s)
    # 统一换行后再压空白（表格单元格常被抽成多行点+字）
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    # 去掉「空行」以及仅残留空白的行
    lines = [ln.strip() for ln in s.split("\n")]
    lines = [ln for ln in lines if ln]
    s = "\n".join(lines)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()
