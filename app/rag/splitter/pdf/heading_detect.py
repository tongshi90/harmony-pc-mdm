"""标题/备注疑似标注：字号 > 真加粗 > 改进版正则；层级事后统一赋值。

识别：
  正文 = 全文字符加权出现最多的字号；
  明显更大 = 疑似标题；明显更小 = 疑似备注；
  同字号整行加粗（短且非连续）= 亦疑似标题；
  其余再走正则章条规则（见 regex_heading）。

定级（``assign_title_levels``）：
  Word 样式 > 正则语义表 > 受限字号分档 > 加粗兜底。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.rag.splitter.pdf.regex_heading import annotate_regex_titles, semantic_level_for_rule

# 与正文字号比较的容差 / 阈值（pt）
SIZE_EQ_TOL = 0.6
TITLE_MIN_DELTA = 1.0  # 至少比正文大这么多才算标题
NOTE_MIN_DELTA = 1.0

# 加粗标题：整行加粗比例、最大长度、连续加粗行不视为标题
BOLD_RATIO_FULL = 0.98
BOLD_TITLE_MAX_CHARS = 40
_BOLD_FONT_RE = re.compile(
    r"(bold|black|heavy|semibold|demibold|italicbold|粗体|黑体)",
    re.IGNORECASE,
)

# 无编号标题：字号分档最多占到的级数；纯加粗兜底级
SIZE_ONLY_MAX_LEVEL = 2
BOLD_FALLBACK_LEVEL = 4



def _round_size(size: float) -> float:
    """字号归并到 0.5pt，减少 10.5/10.49 这类抖动。"""
    return round(float(size) * 2) / 2.0


def _mode_size(sizes: list[float]) -> float | None:
    if not sizes:
        return None
    rounded = [_round_size(s) for s in sizes]
    return Counter(rounded).most_common(1)[0][0]


def _is_bold_font(fontname: str) -> bool:
    return bool(_BOLD_FONT_RE.search(fontname or ""))


def chars_to_lines(
    chars: list[dict[str, Any]],
    *,
    tolerance: float = 3.0,
) -> list[dict[str, Any]]:
    """将 pdfplumber chars 聚合成行，并带上代表字号与加粗比例。"""
    if not chars:
        return []

    groups: list[dict[str, Any]] = []
    for ch in chars:
        text = ch.get("text") or ""
        if not text or text.isspace():
            continue
        top = float(ch["top"])
        found = None
        for g in groups:
            if abs(g["top"] - top) <= tolerance:
                found = g
                break
        if found is None:
            groups.append({"top": top, "chars": [ch]})
        else:
            found["chars"].append(ch)

    groups.sort(key=lambda g: g["top"])
    lines: list[dict[str, Any]] = []
    for g in groups:
        items = sorted(g["chars"], key=lambda c: float(c["x0"]))
        text = "".join(str(c.get("text") or "") for c in items).strip()
        if not text:
            continue
        sizes = [float(c["size"]) for c in items if c.get("size") is not None]
        fonts = [str(c.get("fontname") or "") for c in items]
        bold_flags = [_is_bold_font(fn) for fn in fonts]
        bold_ratio = (sum(1 for x in bold_flags if x) / len(bold_flags)) if bold_flags else 0.0
        size = _mode_size(sizes)
        font = Counter(fonts).most_common(1)[0][0] if fonts else ""
        x0 = min(float(c["x0"]) for c in items)
        x1 = max(float(c["x1"]) for c in items)
        top = min(float(c["top"]) for c in items)
        bottom = max(float(c["bottom"]) for c in items)
        lines.append(
            {
                "text": text,
                "size": size,
                "fontname": font,
                "bold_ratio": bold_ratio,
                "is_full_bold": bold_ratio >= BOLD_RATIO_FULL,
                "bbox": (x0, top, x1, bottom),
                "char_count": len(text),
            }
        )
    return lines


def infer_body_size(lines: list[dict[str, Any]]) -> float | None:
    """按字符数加权，统计出现最多的字号作为正文基准。"""
    counter: Counter[float] = Counter()
    for line in lines:
        size = line.get("size")
        if size is None:
            continue
        counter[_round_size(float(size))] += int(
            line.get("char_count") or len(line.get("text") or "")
        )
    if not counter:
        return None
    body, _n = counter.most_common(1)[0]
    return body


def _mark_bold_title_candidates(lines: list[dict[str, Any]]) -> list[bool]:
    """整行加粗 + 较短 + 前后不与其它整行加粗短行连续 → 候选。

    连续多行整行加粗（即使每行都短）整段不标为加粗标题。
    仅部分加粗 → 不是候选（在 is_full_bold 已排除）。
    """
    n = len(lines)
    eligible = [False] * n
    for i, line in enumerate(lines):
        if not line.get("is_full_bold"):
            continue
        if int(line.get("char_count") or 0) > BOLD_TITLE_MAX_CHARS:
            continue
        eligible[i] = True

    # 找连续 eligible 段：长度 >= 2 则全部取消；长度 == 1 保留
    candidates = [False] * n
    i = 0
    while i < n:
        if not eligible[i]:
            i += 1
            continue
        j = i
        while j < n and eligible[j]:
            j += 1
        if j - i == 1:
            candidates[i] = True
        i = j
    return candidates


def annotate_lines(
    lines: list[dict[str, Any]],
    body_size: float | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """为行打上 role=body|title|note 与 title_via；level 仅作临时值，最终由 assign 覆盖。"""
    meta: dict[str, Any] = {
        "body_size": body_size,
        "title_sizes": [],
        "bold_title_count": 0,
    }
    if not lines:
        return [], meta

    for line in lines:
        line["role"] = "body"
        line["level"] = None
        line["title_via"] = None

    if body_size is None:
        # 无字号基准时仍可尝试纯加粗规则
        bold_flags = _mark_bold_title_candidates(lines)
        for line, is_bold_title in zip(lines, bold_flags):
            if is_bold_title:
                line["role"] = "title"
                line["title_via"] = "bold"
                meta["bold_title_count"] += 1
        return lines, meta

    title_sizes = sorted(
        {
            _round_size(float(l["size"]))
            for l in lines
            if l.get("size") is not None
            and _round_size(float(l["size"])) >= body_size + TITLE_MIN_DELTA
        },
        reverse=True,
    )
    meta["title_sizes"] = title_sizes

    for line in lines:
        size = line.get("size")
        if size is None:
            continue
        rs = _round_size(float(size))
        if rs >= body_size + TITLE_MIN_DELTA:
            line["role"] = "title"
            line["title_via"] = "size"
        elif rs <= body_size - NOTE_MIN_DELTA:
            line["role"] = "note"
            line["level"] = None

    bold_flags = _mark_bold_title_candidates(lines)
    for line, is_bold_title in zip(lines, bold_flags):
        if not is_bold_title:
            continue
        # 已由字号判为标题则保留字号结果，仅补充标记
        if line.get("role") == "title":
            via = line.get("title_via") or "size"
            line["title_via"] = f"{via}+bold" if "bold" not in via else via
            continue
        if line.get("role") == "note":
            continue
        line["role"] = "title"
        line["title_via"] = "bold"
        meta["bold_title_count"] += 1

    return lines, meta


def assign_title_levels(
    lines: list[dict[str, Any]],
    *,
    body_size: float | None = None,
) -> dict[str, Any]:
    """统一写入标题 level：样式 > 正则语义 > 受限字号 > 加粗兜底。"""
    titles = [
        ln
        for ln in lines
        if (ln.get("role") or "") == "title" and not ln.get("_stream_gap")
    ]
    meta: dict[str, Any] = {
        "level_via_style": 0,
        "level_via_regex": 0,
        "level_via_size": 0,
        "level_via_bold": 0,
        "size_only_map": {},
    }
    if not titles:
        return meta

    # 无样式、无语义编号的标题：按字号从大到小映射到 1..SIZE_ONLY_MAX_LEVEL
    size_candidates: list[float] = []
    for ln in titles:
        if ln.get("is_heading_style"):
            continue
        if semantic_level_for_rule(ln.get("regex_rule_id")) is not None:
            continue
        size = ln.get("size")
        if size is None or body_size is None:
            continue
        rs = _round_size(float(size))
        if rs >= float(body_size) + TITLE_MIN_DELTA:
            size_candidates.append(rs)
    size_ranks = sorted(set(size_candidates), reverse=True)
    size_to_level = {
        s: min(i + 1, SIZE_ONLY_MAX_LEVEL) for i, s in enumerate(size_ranks)
    }
    meta["size_only_map"] = {str(k): v for k, v in size_to_level.items()}

    for ln in titles:
        # 1) Word 样式
        if ln.get("is_heading_style"):
            try:
                level = max(int(ln.get("style_level") or ln.get("level") or 1), 1)
            except (TypeError, ValueError):
                level = 1
            ln["level"] = level
            meta["level_via_style"] += 1
            continue

        # 2) 正则语义
        sem = semantic_level_for_rule(ln.get("regex_rule_id"))
        if sem is not None:
            ln["level"] = int(sem)
            meta["level_via_regex"] += 1
            continue

        # 3) 字号分档（仅明显大于正文）
        size = ln.get("size")
        if (
            size is not None
            and body_size is not None
            and _round_size(float(size)) >= float(body_size) + TITLE_MIN_DELTA
        ):
            rs = _round_size(float(size))
            ln["level"] = int(size_to_level.get(rs, SIZE_ONLY_MAX_LEVEL))
            meta["level_via_size"] += 1
            continue

        # 4) 加粗等兜底
        ln["level"] = BOLD_FALLBACK_LEVEL
        meta["level_via_bold"] += 1

    return meta


def assign_title_levels_for_blocks(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """从 blocks 收集文本行并统一定级。"""
    text_lines: list[dict[str, Any]] = []
    for b in blocks:
        if b.get("kind") != "text":
            continue
        for line in b.get("lines") or []:
            text_lines.append(line)
    body_size = infer_body_size(text_lines)
    return assign_title_levels(text_lines, body_size=body_size)


def annotate_document_blocks(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """对文档流做全文统一标注；顺序：字号 → 加粗 → 正则 → 统一定级。

    文本行参与字号/加粗/正则；表格（及预留的图片等）插入流占位，
    供正则冒号抑制判断「冒号与列举标题之间是否还有其它内容」。
    """
    all_lines: list[dict[str, Any]] = []
    text_lines: list[dict[str, Any]] = []
    for b in blocks:
        kind = b.get("kind")
        if kind == "text":
            for line in b.get("lines") or []:
                all_lines.append(line)
                text_lines.append(line)
        elif kind in ("table", "image"):
            # 仅占位，不写回 blocks；image 预留
            all_lines.append({"_stream_gap": kind, "text": ""})

    body_size = infer_body_size(text_lines)
    _, meta = annotate_lines(text_lines, body_size)
    regex_meta = annotate_regex_titles(all_lines)
    meta.update(regex_meta)
    level_meta = assign_title_levels(text_lines, body_size=body_size)
    meta["title_level_assign"] = level_meta
    return meta


def format_line_for_print(line: dict[str, Any]) -> str:
    """方便人工校验：正文/备注前缀在前；标题为「缩进+文本+标记在后」。"""
    text = line.get("text") or ""
    role = line.get("role") or "body"
    size = line.get("size")
    size_s = f"{size:.1f}pt" if isinstance(size, (int, float)) else "?"
    bold_s = ""
    if line.get("is_full_bold"):
        bold_s = " | 整行加粗"
    elif float(line.get("bold_ratio") or 0) > 0.05:
        bold_s = f" | 部分加粗{float(line['bold_ratio']):.0%}"

    if role == "title":
        try:
            level = int(line.get("level") or 1)
        except (TypeError, ValueError):
            level = 1
        level = max(level, 1)
        indent = "    " * (level - 1)
        via = line.get("title_via") or "?"
        marker = f"【疑似标题 L{level} | {size_s} | 依据:{via}{bold_s}】"
        return f"{indent}{text} {marker}"
    if role == "note":
        return f"【疑似备注 | {size_s}{bold_s}】{text}"
    return f"【正文 | {size_s}{bold_s}】{text}"


def render_annotated_document(blocks: list[dict[str, Any]]) -> str:
    """整篇可读文本：文本行带标注；表格/图片整块输出（不按字号拆）。"""
    parts: list[str] = []
    for b in blocks:
        kind = b.get("kind")
        if kind == "text":
            lines = b.get("lines") or []
            if lines:
                for line in lines:
                    parts.append(format_line_for_print(line))
            else:
                text = (b.get("text") or "").strip()
                if text:
                    for row in text.splitlines():
                        if row.strip():
                            parts.append(f"【正文 | ?】{row.strip()}")
        elif kind == "table":
            text = (b.get("text") or "").strip()
            if text:
                parts.append("【表格】")
                parts.append(text)
        elif kind == "image":
            page = b.get("page")
            wh = f"{b.get('width') or '?'}x{b.get('height') or '?'}"
            parts.append(f"【图片 | 第{page}页 | {wh}】")
            text = (b.get("text") or "").strip()
            if text:
                parts.append(text)
            else:
                path = b.get("image_path") or ""
                parts.append(f"（待识别/无文本）{path}".rstrip())
    return "\n".join(parts)


def render_toc_section(blocks: list[dict[str, Any]]) -> str:
    """输出疑似目录区间内的行（由 regex 目录检测打上 in_toc）。"""
    parts: list[str] = []
    for b in blocks:
        if b.get("kind") != "text":
            continue
        for line in b.get("lines") or []:
            if not line.get("in_toc"):
                continue
            text = (line.get("text") or "").strip()
            if text:
                parts.append(f"【疑似目录】{text}")
    return "\n".join(parts)


def render_title_outline(blocks: list[dict[str, Any]]) -> str:
    """仅输出疑似标题行（格式与全文标注一致），便于对照文档检查切分。"""
    parts: list[str] = []
    for b in blocks:
        if b.get("kind") != "text":
            continue
        for line in b.get("lines") or []:
            if (line.get("role") or "") != "title":
                continue
            parts.append(format_line_for_print(line))
    return "\n".join(parts)
