"""页眉页脚 / 页码过滤。

策略：
1. 只在页顶/页底位置带内取候选行
2. 页码：行内可包含页码形态（前后可有其它文案）；用「匹配到的页码片段」
   生成 {N} 模板跨页投票；命中则整行删除
3. 纯数字页码仍要求整行（避免带内普通数字误触）
4. 固定文案：无页码命中时，规范化全文相等 + 跨页高重复 → 删除
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

# 位置带：页高比例
BAND_RATIO = 0.12
# 每端最多参与投票的候选行数
MAX_CANDIDATES_PER_BAND = 3
# 跨页出现比例阈值
MIN_PAGE_RATIO = 0.6
# 短文档至少命中页数
MIN_PAGE_HITS = 3

_DIGIT_RE = re.compile(r"\d+")
_SPACE_RE = re.compile(r"\s+")

# 可「包含匹配」的页码片段（在去空白后的文本上 search）
_PAGE_FRAGMENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"第\d+页"),
    re.compile(r"第\d+頁"),
    re.compile(r"\d+/\d+"),
    re.compile(r"[Pp]age\d+", re.I),
    re.compile(r"-\d+-"),
    re.compile(r"·\d+·"),
]


def _norm_text(text: str) -> str:
    t = (text or "").strip()
    t = _SPACE_RE.sub("", t)
    return t


def _fragment_to_template(fragment: str) -> str:
    return _DIGIT_RE.sub("{N}", _SPACE_RE.sub("", fragment))


def _page_number_template(text: str) -> str | None:
    """从文本中抽出页码模板；前后可有其它文案。

    返回值基于「匹配到的页码片段」做数字槽替换，例如：
    ``5/17（不得外传…）`` → ``{N}/{N}``
    纯数字仅当整行都是数字时才认：``12`` → ``{N}``
    """
    raw = (text or "").strip()
    if not raw:
        return None
    compact = _SPACE_RE.sub("", raw)
    if not compact:
        return None

    # 纯数字：必须整行，避免「包含任意数字」误伤
    if re.fullmatch(r"\d+", compact):
        return "{N}"

    for pattern in _PAGE_FRAGMENT_PATTERNS:
        m = pattern.search(compact)
        if m:
            return _fragment_to_template(m.group(0))

    # 短行兜底：去数字后只剩页码常用符号
    if len(compact) <= 12 and _DIGIT_RE.search(compact):
        stripped = _DIGIT_RE.sub("", compact)
        if stripped == "" or re.fullmatch(r"[第页頁/\-·.Pagepage]+", stripped or ""):
            return _DIGIT_RE.sub("{N}", compact)
    return None


def _band_of_line(line: dict[str, Any], page_height: float) -> str | None:
    bbox = line.get("bbox")
    if not bbox or page_height <= 0:
        return None
    top = float(bbox[1])
    bottom = float(bbox[3])
    mid = (top + bottom) / 2.0
    if mid <= page_height * BAND_RATIO:
        return "top"
    if mid >= page_height * (1.0 - BAND_RATIO):
        return "bottom"
    return None


def _enough_hits(hit_pages: int, total_pages: int) -> bool:
    if total_pages <= 0 or hit_pages <= 0:
        return False
    if hit_pages >= MIN_PAGE_HITS:
        return True
    return (hit_pages / total_pages) >= MIN_PAGE_RATIO


def detect_header_footer_patterns(
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    """从多页原始行中投票得到页码模板与固定眉脚文案。

    pages 项: {page, page_height, lines: [...]}
    """
    total_pages = len(pages)
    # (band, template) -> set(page)
    page_tmpl_pages: dict[tuple[str, str], set[int]] = defaultdict(set)
    # (band, norm_text) -> set(page)
    fixed_pages: dict[tuple[str, str], set[int]] = defaultdict(set)
    page_tmpl_samples: dict[tuple[str, str], str] = {}
    fixed_samples: dict[tuple[str, str], str] = {}

    for page in pages:
        page_no = int(page.get("page") or 0)
        page_height = float(page.get("page_height") or 0)
        lines = list(page.get("lines") or [])
        top_cands: list[dict[str, Any]] = []
        bottom_cands: list[dict[str, Any]] = []
        for line in lines:
            band = _band_of_line(line, page_height)
            if band == "top":
                top_cands.append(line)
            elif band == "bottom":
                bottom_cands.append(line)

        top_cands.sort(key=lambda l: float(l["bbox"][1]))
        bottom_cands.sort(key=lambda l: -float(l["bbox"][1]))
        top_cands = top_cands[:MAX_CANDIDATES_PER_BAND]
        bottom_cands = bottom_cands[:MAX_CANDIDATES_PER_BAND]

        for band, cands in (("top", top_cands), ("bottom", bottom_cands)):
            for line in cands:
                text = str(line.get("text") or "").strip()
                if not text:
                    continue
                tmpl = _page_number_template(text)
                if tmpl:
                    key = (band, tmpl)
                    page_tmpl_pages[key].add(page_no)
                    page_tmpl_samples.setdefault(key, text)
                    continue
                # 固定文案（未识别为页码）；不设长度上限
                norm = _norm_text(text)
                if not norm or len(norm) < 2:
                    continue
                key = (band, norm)
                fixed_pages[key].add(page_no)
                fixed_samples.setdefault(key, text)

    page_templates: list[dict[str, Any]] = []
    for (band, tmpl), pageset in page_tmpl_pages.items():
        if _enough_hits(len(pageset), total_pages):
            page_templates.append(
                {
                    "band": band,
                    "template": tmpl,
                    "hits": len(pageset),
                    "sample": page_tmpl_samples.get((band, tmpl), ""),
                }
            )

    fixed_texts: list[dict[str, Any]] = []
    for (band, norm), pageset in fixed_pages.items():
        if _enough_hits(len(pageset), total_pages):
            fixed_texts.append(
                {
                    "band": band,
                    "norm": norm,
                    "hits": len(pageset),
                    "sample": fixed_samples.get((band, norm), ""),
                }
            )

    return {
        "total_pages": total_pages,
        "page_templates": page_templates,
        "fixed_texts": fixed_texts,
    }


def _match_page_template(text: str, template: str) -> bool:
    """行内抽出的页码模板是否等于已投票模板（混合行整行可删）。"""
    tmpl = _page_number_template(text)
    return tmpl is not None and tmpl == template


def is_header_footer_line(
    line: dict[str, Any],
    *,
    page_height: float,
    patterns: dict[str, Any],
) -> bool:
    """单行是否应作为眉脚/页码丢弃。"""
    band = _band_of_line(line, page_height)
    if not band:
        return False
    text = str(line.get("text") or "").strip()
    if not text:
        return False

    for item in patterns.get("page_templates") or []:
        if item.get("band") != band:
            continue
        if _match_page_template(text, str(item.get("template") or "")):
            return True

    norm = _norm_text(text)
    for item in patterns.get("fixed_texts") or []:
        if item.get("band") != band:
            continue
        if norm == item.get("norm"):
            return True
    return False


def filter_page_lines(
    lines: list[dict[str, Any]],
    *,
    page_height: float,
    patterns: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """过滤一页中的眉脚/页码行，返回 (保留行, 删除数)。"""
    kept: list[dict[str, Any]] = []
    removed = 0
    for line in lines:
        if is_header_footer_line(line, page_height=page_height, patterns=patterns):
            removed += 1
            continue
        kept.append(line)
    return kept, removed
