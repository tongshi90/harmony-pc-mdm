"""改进版正则标题判定（字号/加粗之后的第三层）。

约定（已确认）：
- 标题最大长度：入样行长精确众数（写满一行）× 80%；推不出则回退 40
- 启用章/节/篇/部分/条、一、、（一）；关闭 NUM_SIMPLE / 光秃 1.1 / ^\\d+、
- 本模块只负责「是否标题」+ ``regex_rule_id``；层级由
  ``heading_detect.assign_title_levels`` 按语义表统一赋值
- 冒号抑制仅作用于列举型（CN_LIST / CN_PAREN）：
  仅当冒号行与候选列举标题之间没有任何其它内容
  （正文/备注行、表格、图片等流占位）时才抑制；中间有内容则不抑制
- TOC 内不开片

- 文档级规则开关（宁可不切）：M≥MIN_MATCH 且 T/M < MIN_ENABLE_RATE → 整规则禁用
  （中间带也关；不再单独配置 KEEP_RATE）
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

MIN_TITLE_CHARS = 2
FALLBACK_MAX_TITLE_CHARS = 40
FULL_LINE_RATIO = 0.8
TOC_MIN_CONSECUTIVE = 2
# 数字占比过高的行不参与众数（如编号密集行）
_DIGIT_RATIO_SKIP = 0.55
# 「写满行」众数若过小，视为样本异常，回退固定上限
_MIN_RELIABLE_FULL_LINE = 12

# 文档级规则开关：匹配够多时，仅当「像标题比例」足够高才启用该 rule
# （原 DROP + 中间带一律禁用；不再单独配置 KEEP/DROP 双阈值）
MIN_MATCH = 4
MIN_ENABLE_RATE = 0.6

# 中文数字
_CN_NUM = r"[一二三四五六七八九十百千万两〇零]+"

# (rule_id, pattern, is_list_style)
_RULES: list[tuple[str, re.Pattern[str], bool]] = [
    ("CN_CHAPTER", re.compile(rf"^第{_CN_NUM}章\s*.*"), False),
    ("NUM_CHAPTER", re.compile(r"^第\d+章\s*.*"), False),
    ("CN_PART", re.compile(rf"^第{_CN_NUM}部分\s*.*"), False),
    ("NUM_PART", re.compile(r"^第\d+部分\s*.*"), False),
    ("CN_ARTICLE", re.compile(rf"^第{_CN_NUM}篇\s*.*"), False),
    ("NUM_ARTICLE", re.compile(r"^第\d+篇\s*.*"), False),
    ("CN_SECTION", re.compile(rf"^第{_CN_NUM}节\s*.*"), False),
    ("NUM_SECTION", re.compile(r"^第\d+节\s*.*"), False),
    ("CN_ITEM", re.compile(rf"^第{_CN_NUM}条\s*.*"), False),
    ("NUM_ITEM", re.compile(r"^第\d+条\s*.*"), False),
    ("CN_LIST", re.compile(rf"^{_CN_NUM}、\s*.*"), True),
    ("CN_PAREN", re.compile(rf"^[（(]{_CN_NUM}[）)]\s*.*"), True),
]

# 语义层级（固定；不按文中首次出现顺序）
RULE_SEMANTIC_LEVEL: dict[str, int] = {
    "CN_CHAPTER": 1,
    "NUM_CHAPTER": 1,
    "CN_PART": 1,
    "NUM_PART": 1,
    "CN_ARTICLE": 1,
    "NUM_ARTICLE": 1,
    "CN_SECTION": 2,
    "NUM_SECTION": 2,
    "CN_ITEM": 3,
    "NUM_ITEM": 3,
    "CN_LIST": 4,
    "CN_PAREN": 5,
}


def semantic_level_for_rule(rule_id: str | None) -> int | None:
    if not rule_id:
        return None
    return RULE_SEMANTIC_LEVEL.get(str(rule_id))


_PAGE_TAIL_RE = re.compile(r"(?:第\s*\d+\s*页|\d+)\s*$")
_SENTENCE_END_RE = re.compile(r"[。！？]$")
_COLON_END_RE = re.compile(r"[：:]\s*$")
_TOC_LABEL_RE = re.compile(r"^目\s*录$")
_DIGIT_RE = re.compile(r"\d")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def match_title_rule(text: str) -> tuple[str | None, bool]:
    """返回 (rule_id, is_list_style)；未命中则为 (None, False)。"""
    clean = _clean(text)
    if not clean:
        return None, False
    for rule_id, pattern, is_list in _RULES:
        if pattern.match(clean):
            return rule_id, is_list
    return None, False


def _digit_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(_DIGIT_RE.findall(text)) / max(len(text), 1)


def infer_full_line_chars(lines: list[dict[str, Any]]) -> tuple[int | None, dict[str, Any]]:
    """推断本文「写满一行」的字数 = 入样行长的精确众数。

    入样：去掉过短行、数字占比过高行；不再剔长/偏长过滤。
    制度正文多数行写满，众数即一行最多能写多少字。
    并列最多时取更长的那个。众数过小则回退固定上限。
    """
    lengths: list[int] = []
    for line in lines:
        text = _clean(str(line.get("text") or ""))
        if len(text) < MIN_TITLE_CHARS:
            continue
        if _digit_ratio(text) >= _DIGIT_RATIO_SKIP:
            continue
        lengths.append(len(text))

    info: dict[str, Any] = {
        "sample_lines": len(lengths),
        "full_line_chars": None,
        "max_title_chars": FALLBACK_MAX_TITLE_CHARS,
        "used_fallback": True,
    }
    if len(lengths) < 5:
        return None, info

    counts = Counter(lengths)
    top_freq = counts.most_common(1)[0][1]
    # 并列最多 → 取更长（更接近「一行最多能写多少字」）
    full = max(n for n, c in counts.items() if c == top_freq)
    if full < _MIN_RELIABLE_FULL_LINE:
        info["rejected_full_line_chars"] = full
        info["length_top"] = counts.most_common(5)
        return None, info

    max_title = max(MIN_TITLE_CHARS + 1, int(math.floor(full * FULL_LINE_RATIO)))
    info.update(
        {
            "full_line_chars": full,
            "max_title_chars": max_title,
            "used_fallback": False,
            "mode_freq": top_freq,
            "length_top": counts.most_common(5),
        }
    )
    return full, info


def _passes_line_filter(
    text: str,
    max_title_chars: int,
    *,
    allow_sentence_end: bool = False,
) -> bool:
    """行长等过滤。强结构标题（章/条等）可允许行尾句号。"""
    clean = _clean(text)
    n = len(clean)
    if n < MIN_TITLE_CHARS or n > max_title_chars:
        return False
    if not allow_sentence_end and _SENTENCE_END_RE.search(clean):
        return False
    return True


def _title_core_for_toc(text: str) -> str | None:
    """去掉行尾页码，得到目录条目核心。"""
    clean = _clean(text)
    if not _PAGE_TAIL_RE.search(clean):
        return None
    core = _PAGE_TAIL_RE.sub("", clean).strip()
    core = re.sub(r"[.\-—_·•\s]+$", "", core).strip()
    return core or None


def detect_toc_range(lines: list[dict[str, Any]]) -> tuple[int, int] | None:
    """返回 TOC 闭区间 [start, end]（0-based，含端点）；无则 None。"""
    n = len(lines)
    consecutive = 0
    toc_start: int | None = None

    for i in range(n):
        text = _clean(str(lines[i].get("text") or ""))
        rule_id, _ = match_title_rule(text)
        core = _title_core_for_toc(text) if rule_id else None
        reappears = False
        if core:
            for j in range(i + 1, n):
                later = _clean(str(lines[j].get("text") or ""))
                if core and core in later:
                    reappears = True
                    break

        if rule_id and core and reappears:
            if consecutive == 0:
                toc_start = i
            consecutive += 1
            if consecutive >= TOC_MIN_CONSECUTIVE and toc_start is not None:
                start = toc_start
                if start > 0 and _TOC_LABEL_RE.match(
                    _clean(str(lines[start - 1].get("text") or ""))
                ):
                    start = start - 1
                first_core = _title_core_for_toc(
                    _clean(str(lines[toc_start].get("text") or ""))
                )
                end = toc_start
                if first_core:
                    for j in range(toc_start + 1, n):
                        later = _clean(str(lines[j].get("text") or ""))
                        if first_core in later and not _title_core_for_toc(later):
                            end = j - 1
                            break
                    else:
                        end = min(toc_start + 30, n - 1)
                else:
                    end = min(toc_start + 30, n - 1)
                return (start, max(start, end))
        else:
            consecutive = 0
            toc_start = None

    return None


def _prev_effective_text(lines: list[dict[str, Any]], idx: int) -> str:
    """上一有效文本（跳过空行与流占位）；仅用于调试/兼容。"""
    j = idx - 1
    while j >= 0:
        if lines[j].get("_stream_gap"):
            j -= 1
            continue
        t = _clean(str(lines[j].get("text") or ""))
        if t:
            return t
        j -= 1
    return ""


def _colon_should_suppress_list(
    lines: list[dict[str, Any]],
    idx: int,
    *,
    rule_id: str,
    suppress_list_rule: str | None,
) -> bool:
    """列举型冒号抑制。

    - 同一 rule 在冒号引导下连续列举：继续抑制
    - 否则仅当「紧邻的上一内容」是以冒号结尾的文本才抑制
    - 若回溯时先碰到表格/图片等流占位，或先碰到非冒号文本 → 不抑制
    """
    if suppress_list_rule == rule_id:
        return True
    j = idx - 1
    while j >= 0:
        item = lines[j]
        if item.get("_stream_gap"):
            # 冒号与候选之间已有表格/图片等
            return False
        t = _clean(str(item.get("text") or ""))
        if not t:
            j -= 1
            continue
        return bool(_COLON_END_RE.search(t))
    return False


def _decide_enabled_rules(
    match_total: dict[str, int],
    match_title_like: dict[str, int],
) -> tuple[set[str], dict[str, Any]]:
    """文档级：匹配够多且像标题比例不足 → 整规则禁用。"""
    enabled: set[str] = set()
    detail: dict[str, Any] = {}
    for rule_id, m in match_total.items():
        t = int(match_title_like.get(rule_id) or 0)
        rate = (t / m) if m else 0.0
        if m < MIN_MATCH:
            on = True
            reason = f"样本少(M={m}<{MIN_MATCH})，不做比例禁用"
        elif rate >= MIN_ENABLE_RATE:
            on = True
            reason = f"通过率高(T/M={t}/{m}={rate:.2f}>={MIN_ENABLE_RATE})"
        else:
            on = False
            reason = (
                f"通过率不足(T/M={t}/{m}={rate:.2f}<{MIN_ENABLE_RATE})，"
                f"本文更像说明/条款体例，整规则禁用"
            )
        if on:
            enabled.add(rule_id)
        detail[rule_id] = {
            "match_total": m,
            "title_like": t,
            "rate": round(rate, 4),
            "enabled": on,
            "reason": reason,
        }
    return enabled, detail


def annotate_regex_titles(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """在已有 size/bold 标注之后，补充 regex 标题。"""
    meta: dict[str, Any] = {
        "regex_title_count": 0,
        "regex_suppressed_colon": 0,
        "regex_toc_range": None,
        "regex_rule_levels": {},
        "regex_rule_gate": {},
    }
    if not lines:
        return meta

    _full, len_info = infer_full_line_chars(lines)
    max_title_chars = int(len_info["max_title_chars"])
    meta["regex_line_len"] = len_info

    toc = detect_toc_range(lines)
    meta["regex_toc_range"] = toc
    toc_set: set[int] = set(range(toc[0], toc[1] + 1)) if toc else set()
    for i, line in enumerate(lines):
        line["in_toc"] = i in toc_set

    # ---------- Pass1：按 rule 统计裸命中 M / 像标题 T ----------
    match_total: dict[str, int] = {}
    match_title_like: dict[str, int] = {}
    # 预计算每行：rule、是否像标题、是否冒号抑制
    row_info: list[dict[str, Any]] = []
    suppress_list_rule: str | None = None

    for i, line in enumerate(lines):
        info: dict[str, Any] = {
            "rule_id": None,
            "is_list": False,
            "title_like": False,
            "colon_suppressed": False,
        }
        # 表格/图片等流占位：打断冒号连续抑制，本身不参与标题
        if line.get("_stream_gap"):
            suppress_list_rule = None
            row_info.append(info)
            continue

        text = _clean(str(line.get("text") or ""))
        if i in toc_set:
            suppress_list_rule = None
            row_info.append(info)
            continue

        rule_id, is_list = match_title_rule(text)
        info["rule_id"] = rule_id
        info["is_list"] = is_list
        if not rule_id:
            suppress_list_rule = None
            row_info.append(info)
            continue

        match_total[rule_id] = match_total.get(rule_id, 0) + 1

        passes = _passes_line_filter(
            text,
            max_title_chars,
            allow_sentence_end=not is_list,
        )
        if is_list:
            if _colon_should_suppress_list(
                lines,
                i,
                rule_id=rule_id,
                suppress_list_rule=suppress_list_rule,
            ):
                suppress_list_rule = rule_id
                info["colon_suppressed"] = True
                row_info.append(info)
                continue
            suppress_list_rule = None
        else:
            suppress_list_rule = None

        if passes:
            info["title_like"] = True
            match_title_like[rule_id] = match_title_like.get(rule_id, 0) + 1
        row_info.append(info)

    enabled, gate_detail = _decide_enabled_rules(match_total, match_title_like)
    meta["regex_rule_gate"] = gate_detail

    # ---------- Pass2：仅对启用 rule 落「是标题」；层级留给 assign_title_levels ----------
    for i, line in enumerate(lines):
        info = row_info[i]
        rule_id = info.get("rule_id")
        line["regex_rule_id"] = rule_id

        if not rule_id or rule_id not in enabled:
            continue
        if info.get("colon_suppressed"):
            meta["regex_suppressed_colon"] += 1
            continue
        if not info.get("title_like"):
            continue

        already_title = line.get("role") == "title"
        if already_title:
            via = line.get("title_via") or ""
            if "regex" not in via:
                line["title_via"] = f"{via}+regex" if via else "regex"
            continue

        # 小字备注仅展示用，业务上当正文，不抬升为正则标题
        if line.get("role") == "note":
            continue

        line["role"] = "title"
        line["title_via"] = "regex"
        meta["regex_title_count"] += 1

    meta["regex_rule_levels"] = {
        rid: RULE_SEMANTIC_LEVEL[rid]
        for rid in sorted(enabled)
        if rid in RULE_SEMANTIC_LEVEL
    }
    return meta
