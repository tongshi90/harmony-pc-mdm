"""Word 原生表格 → 二维矩阵文本。"""

from __future__ import annotations

from typing import Any

from app.rag.splitter.pdf.table_merge import format_rows
from app.rag.splitter.pdf.text_clean import clean_extracted_text


def _grid_span(tc: Any) -> int:
    try:
        tcPr = tc.tcPr
        if tcPr is not None and tcPr.gridSpan is not None and tcPr.gridSpan.val is not None:
            return max(int(tcPr.gridSpan.val), 1)
    except Exception:
        pass
    return 1


def _vmerge_kind(tc: Any) -> str | None:
    """返回 None / 'restart' / 'continue'。"""
    try:
        tcPr = tc.tcPr
        if tcPr is None or tcPr.vMerge is None:
            return None
        val = tcPr.vMerge.val
        # OOXML: 缺省 val 表示 continue
        if val is None or str(val).lower() == "continue":
            return "continue"
        return "restart"
    except Exception:
        return None


def _tc_plain_text(tc: Any) -> str:
    """只读本 tc 内 w:t，避免依赖 python-docx 对续合并格的继承行为。"""
    try:
        from docx.oxml.ns import qn

        parts = [t.text or "" for t in tc.iter(qn("w:t"))]
        return clean_extracted_text("".join(parts))
    except Exception:
        return ""


def extract_table_matrix(table: Any) -> list[list[str]]:
    """将 python-docx Table 转为行列矩阵。

    合并单元格与 PDF 对齐：覆盖范围内所有格子填同一文本
    （横向 gridSpan / 同一 ``_tc`` 展开；纵向 vMerge 向下回填）。
    """
    # 先按 row.cells 展开列宽，并让同一 _tc 的横向占位同值填充
    grid: list[list[str]] = []
    for row in table.rows:
        cells = list(row.cells)
        tc_text: dict[int, str] = {}
        for cell in cells:
            tc_id = id(cell._tc)
            text = clean_extracted_text(cell.text or "")
            prev = tc_text.get(tc_id, "")
            if text and not prev:
                tc_text[tc_id] = text
            elif tc_id not in tc_text:
                tc_text[tc_id] = text
        row_out = [tc_text[id(cell._tc)] for cell in cells]
        grid.append(row_out)

    if not grid:
        return []

    n_cols = max((len(r) for r in grid), default=0)
    for r in grid:
        if len(r) < n_cols:
            r.extend([""] * (n_cols - len(r)))

    # 纵向合并：按物理 tc 的 vMerge + gridSpan，把 restart 文本填满覆盖列
    # active[c] = 当前列纵向合并进行中的文本
    active: list[str | None] = [None] * n_cols
    for ri, row in enumerate(table.rows):
        col = 0
        for tc in row._tr.tc_lst:
            span = _grid_span(tc)
            kind = _vmerge_kind(tc)
            plain = _tc_plain_text(tc)
            # 续合并格自身常无字；用 active 或本格 plain / 已有 grid 值
            if kind == "continue":
                fill = None
                for c in range(col, min(col + span, n_cols)):
                    if active[c]:
                        fill = active[c]
                        break
                if not fill:
                    fill = plain
                if fill:
                    for c in range(col, min(col + span, n_cols)):
                        grid[ri][c] = fill
                        active[c] = fill
            elif kind == "restart":
                fill = plain or next(
                    (grid[ri][c] for c in range(col, min(col + span, n_cols)) if grid[ri][c]),
                    "",
                )
                for c in range(col, min(col + span, n_cols)):
                    if fill:
                        grid[ri][c] = fill
                    active[c] = fill or None
            else:
                # 非纵向合并：结束这些列上的 active
                fill = plain or next(
                    (grid[ri][c] for c in range(col, min(col + span, n_cols)) if grid[ri][c]),
                    "",
                )
                for c in range(col, min(col + span, n_cols)):
                    if fill and not grid[ri][c]:
                        grid[ri][c] = fill
                    active[c] = None
            col += span

    return [r for r in grid if any(c.strip() for c in r)]


def table_to_block(table: Any, *, index: int) -> dict[str, Any] | None:
    rows = extract_table_matrix(table)
    text = format_rows(rows)
    if not text.strip():
        return None
    return {
        "kind": "table",
        "page": None,
        "index": index,
        "bbox": None,
        "rows": rows,
        "text": text,
    }
