"""跨页续表合并：判断是否同一张表，以及下页首行是重复表头还是数据行。

不做 100% 保证；吃不准时默认合并且保留首行（避免误删数据），并打标 uncertain。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from app.rag.splitter.pdf.text_clean import clean_extracted_text

logger = logging.getLogger(__name__)

# 位置：距页顶/页底多少比例算「贴边」
NEAR_EDGE_RATIO = 0.12
# 列宽对齐：允许的相对误差（相对页宽）
COL_ALIGN_TOL_RATIO = 0.04
# 单元格文本相似度
CELL_SIM_THRESHOLD = 0.86

HeaderVerdict = Literal["repeated_header", "data_row", "uncertain"]
MergeVerdict = Literal["merge", "separate", "uncertain_merge"]


def _norm_cell(value: Any) -> str:
    s = clean_extracted_text(value)
    s = s.replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_row(row: list[Any] | None) -> list[str]:
    if not row:
        return []
    return [_norm_cell(c) for c in row]


def _row_key(row: list[Any] | None) -> str:
    return " | ".join(_norm_row(row))


def _cell_sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    # 简单字符级 Jaccard，避免再引第三方依赖
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(len(sa | sb), 1)


def _row_sim(a: list[Any] | None, b: list[Any] | None) -> float:
    ra, rb = _norm_row(a), _norm_row(b)
    if not ra or not rb:
        return 0.0
    n = max(len(ra), len(rb))
    # 列数不同先按位对齐，缺的当空串
    scores = []
    for i in range(n):
        ca = ra[i] if i < len(ra) else ""
        cb = rb[i] if i < len(rb) else ""
        scores.append(_cell_sim(ca, cb))
    return sum(scores) / len(scores)


_HEADERISH = re.compile(
    r"(序号|编号|名称|部门|职责|权限|备注|说明|类型|日期|金额|状态|标题|内容)"
)
_DATAISH_START = re.compile(r"^(\d+|[（(]?\d+[）)]|[一二三四五六七八九十]+、)")


def classify_first_row(
    prev_rows: list[list[Any]],
    next_rows: list[list[Any]],
) -> tuple[HeaderVerdict, str]:
    """判断下表首行：重复表头 / 数据行 / 不确定。"""
    if not prev_rows or not next_rows:
        return "uncertain", "缺行列，无法判断"

    prev_header = prev_rows[0]
    next_first = next_rows[0]
    sim_header = _row_sim(prev_header, next_first)

    # A. 与上页表头高度相似 → 重复表头
    if sim_header >= CELL_SIM_THRESHOLD:
        return (
            "repeated_header",
            f"下页首行与上页表头相似 sim={sim_header:.2f}",
        )

    # B. 与上页任一数据行很像，且不像表头 → 更像数据（少见，但可排除表头）
    data_sims = [_row_sim(r, next_first) for r in prev_rows[1:6]]
    max_data_sim = max(data_sims) if data_sims else 0.0

    next_cells = _norm_row(next_first)
    joined = "".join(next_cells)
    headerish_hits = sum(1 for c in next_cells if _HEADERISH.search(c))
    dataish = bool(next_cells and _DATAISH_START.match(next_cells[0]))
    avg_len = sum(len(c) for c in next_cells) / max(len(next_cells), 1)

    # C. 强数据形态：首格是序号/数字，且不像列名堆
    if dataish and headerish_hits == 0 and sim_header < 0.5:
        return (
            "data_row",
            f"首格像序号且非列名堆 dataish=1 headerish=0 sim_header={sim_header:.2f}",
        )

    # D. 很长的单元格更像内容
    if avg_len >= 25 and sim_header < 0.45 and headerish_hits <= 1:
        return (
            "data_row",
            f"单元格偏长 avg_len={avg_len:.1f} sim_header={sim_header:.2f}",
        )

    # E. 很像列名、短文本、无序号 → 仍可能是另一张表的新表头（不一定是续表）
    if headerish_hits >= 2 and avg_len <= 12 and not dataish:
        return (
            "uncertain",
            f"像表头但与上页表头不同 sim_header={sim_header:.2f} "
            f"headerish={headerish_hits}（可能是新表）",
        )

    if max_data_sim >= 0.75 and sim_header < 0.4:
        return (
            "data_row",
            f"与上页数据行相似 max_data_sim={max_data_sim:.2f}",
        )

    return (
        "uncertain",
        f"无法确信 sim_header={sim_header:.2f} max_data_sim={max_data_sim:.2f} "
        f"headerish={headerish_hits} dataish={int(dataish)} avg_len={avg_len:.1f}",
    )


def _col_count(rows: list[list[Any]]) -> int:
    if not rows:
        return 0
    return max((len(r) for r in rows if r), default=0)


def _near_bottom(bbox: tuple[float, float, float, float], page_height: float) -> bool:
    _x0, _top, _x1, bottom = bbox
    return (page_height - bottom) <= page_height * NEAR_EDGE_RATIO


def _near_top(bbox: tuple[float, float, float, float], page_height: float) -> bool:
    _x0, top, _x1, _bottom = bbox
    return top <= page_height * NEAR_EDGE_RATIO


def _cols_aligned(
    bbox_a: tuple[float, float, float, float],
    bbox_b: tuple[float, float, float, float],
    page_width: float,
) -> bool:
    """用表整体左右边界近似列对齐（无逐列线时的弱信号）。"""
    tol = max(page_width * COL_ALIGN_TOL_RATIO, 8.0)
    return abs(bbox_a[0] - bbox_b[0]) <= tol and abs(bbox_a[2] - bbox_b[2]) <= tol


_CONTINUED_HINT = re.compile(r"(续表|续上表|表\s*续|（续）|\(续\))")


def _has_continued_hint(*texts: str) -> bool:
    return any(_CONTINUED_HINT.search(t or "") for t in texts)


def should_merge_tables(
    prev: dict[str, Any],
    nxt: dict[str, Any],
    *,
    text_between: str = "",
) -> tuple[MergeVerdict, HeaderVerdict, str]:
    """判断 prev(上页表) 与 nxt(下页表) 是否应合并，并给出首行裁决。"""
    prev_rows = prev.get("rows") or []
    next_rows = nxt.get("rows") or []
    reasons: list[str] = []

    # 必须跨页且页码相邻
    if int(nxt.get("page") or 0) != int(prev.get("page") or 0) + 1:
        return "separate", "uncertain", "非相邻页"

    # 两表之间只要有正文（含小字备注等正常内容；眉脚/页码已在上游去掉），
    # 即视为独立两张表，不再合并。
    between = (text_between or "").strip()
    if between:
        preview = between.replace("\n", " ")
        if len(preview) > 40:
            preview = preview[:40] + "..."
        return (
            "separate",
            "uncertain",
            f"两表之间存在正文，视为独立表；between={preview!r}",
        )

    header_v, header_reason = classify_first_row(prev_rows, next_rows)

    prev_bbox = prev.get("bbox")
    next_bbox = nxt.get("bbox")
    prev_ph = float(prev.get("page_height") or 0)
    next_ph = float(nxt.get("page_height") or 0)
    page_width = float(prev.get("page_width") or next.get("page_width") or 0)

    pos_ok = False
    if prev_bbox and next_bbox and prev_ph and next_ph:
        pos_ok = _near_bottom(prev_bbox, prev_ph) and _near_top(next_bbox, next_ph)
        reasons.append(f"贴边位置={'是' if pos_ok else '否'}")

    col_prev = _col_count(prev_rows)
    col_next = _col_count(next_rows)
    col_ok = col_prev > 0 and col_prev == col_next
    reasons.append(f"列数 {col_prev} vs {col_next} => {'同' if col_ok else '不同'}")

    align_ok = False
    if prev_bbox and next_bbox and page_width:
        align_ok = _cols_aligned(prev_bbox, next_bbox, page_width)
        reasons.append(f"左右边界对齐={'是' if align_ok else '否'}")

    hint = _has_continued_hint(
        text_between,
        _row_key(next_rows[0]) if next_rows else "",
        nxt.get("text") or "",
    )
    if hint:
        reasons.append("发现续表字样")

    # 决策
    if not col_ok:
        return "separate", header_v, "列数不同，视为独立表；" + "；".join(reasons)

    strong = hint or (pos_ok and align_ok) or (
        pos_ok and header_v == "repeated_header"
    )
    medium = pos_ok or align_ok or header_v in ("repeated_header", "data_row")

    detail = f"{header_reason}；" + "；".join(reasons)

    if strong and header_v != "uncertain":
        return "merge", header_v, detail
    if strong and header_v == "uncertain":
        # 结构很像续表，但首行吃不准 → 合并且保留首行
        return "uncertain_merge", header_v, detail
    if medium and header_v == "repeated_header":
        return "merge", header_v, detail
    if medium and header_v == "data_row" and pos_ok:
        return "merge", header_v, detail
    if medium:
        return "uncertain_merge", header_v, detail

    # 像新表头且位置也不贴边
    if header_v == "uncertain" and "可能是新表" in header_reason:
        return "separate", header_v, detail

    return "separate", header_v, detail


def merge_table_rows(
    prev_rows: list[list[Any]],
    next_rows: list[list[Any]],
    header_verdict: HeaderVerdict,
) -> list[list[Any]]:
    if not next_rows:
        return list(prev_rows)
    if header_verdict == "repeated_header":
        return list(prev_rows) + list(next_rows[1:])
    # data_row / uncertain：不删首行，避免误删数据
    return list(prev_rows) + list(next_rows)


def format_rows(rows: list[list[Any]] | None) -> str:
    if not rows:
        return ""
    lines: list[str] = []
    for row in rows:
        cells = [_norm_cell(c) for c in row]
        if not any(cells):
            continue
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def merge_cross_page_tables(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对 block 列表做跨页续表合并，返回新列表（含 text block，顺序尽量保持）。"""
    if not blocks:
        return []

    # 按页分组，页内按 top 排序（无 bbox 的 text 放后面）
    by_page: dict[int, list[dict[str, Any]]] = {}
    for b in blocks:
        by_page.setdefault(int(b.get("page") or 0), []).append(b)

    for page in by_page:
        by_page[page].sort(
            key=lambda b: (
                float(b["bbox"][1]) if b.get("bbox") else 1e18,
                float(b["bbox"][0]) if b.get("bbox") else 1e18,
                0 if b.get("kind") == "table" else 1,
            )
        )

    pages = sorted(by_page.keys())
    merged_flags: set[int] = set()  # id of consumed next-table blocks
    out: list[dict[str, Any]] = []

    # 用对象 id 标记被吞并的下页表
    for i, page in enumerate(pages):
        page_blocks = by_page[page]
        for bi, block in enumerate(page_blocks):
            if id(block) in merged_flags:
                continue

            if block.get("kind") != "table":
                out.append(block)
                continue

            # 尝试与下一页「第一张表」合并
            consumed = block
            while True:
                next_page = int(consumed.get("page") or 0) + 1
                if next_page not in by_page:
                    break
                next_tables = [
                    b
                    for b in by_page[next_page]
                    if b.get("kind") == "table" and id(b) not in merged_flags
                ]
                if not next_tables:
                    break
                # 下一页最上边的表
                nxt = min(
                    next_tables,
                    key=lambda b: float(b["bbox"][1]) if b.get("bbox") else 0.0,
                )

                # 收集两表之间的文本（上页表下方 + 下页表上方）
                text_between_parts: list[str] = []
                # 仅第一次跳跃时看「上页表下方」；已合并出的新 dict 不在 by_page 里
                if not consumed.get("merged_from"):
                    cur_page_blocks = by_page.get(int(consumed["page"]), [])
                    try:
                        cur_idx = cur_page_blocks.index(consumed)
                    except ValueError:
                        cur_idx = len(cur_page_blocks) - 1
                    for b in cur_page_blocks[cur_idx + 1 :]:
                        if b.get("kind") == "text":
                            text_between_parts.append(b.get("text") or "")

                try:
                    nxt_idx = by_page[next_page].index(nxt)
                except ValueError:
                    nxt_idx = 0
                for b in by_page[next_page][:nxt_idx]:
                    if b.get("kind") == "text":
                        text_between_parts.append(b.get("text") or "")

                text_between = "\n".join(t for t in text_between_parts if t.strip())
                verdict, header_v, detail = should_merge_tables(
                    consumed, nxt, text_between=text_between
                )

                logger.debug(
                    "[pdf][续表] p%s表#%s + p%s表#%s => %s | 首行=%s | %s",
                    consumed.get("page"),
                    consumed.get("index"),
                    nxt.get("page"),
                    nxt.get("index"),
                    verdict,
                    header_v,
                    detail,
                )

                if verdict == "separate":
                    break

                new_rows = merge_table_rows(
                    consumed.get("rows") or [],
                    nxt.get("rows") or [],
                    header_v,
                )
                merged_flags.add(id(nxt))
                consumed = {
                    **consumed,
                    "rows": new_rows,
                    "text": format_rows(new_rows),
                    "page_end": nxt.get("page"),
                    "merged_from": list(consumed.get("merged_from") or [])
                    + [f"p{nxt.get('page')}#{nxt.get('index')}"],
                    "merge_meta": {
                        "verdict": verdict,
                        "header_verdict": header_v,
                        "detail": detail,
                    },
                    # bbox 保留首页表位置；高度信息保留首页
                }
                # 连续跨多页：继续 while
                continue

            out.append(consumed)

    return out
