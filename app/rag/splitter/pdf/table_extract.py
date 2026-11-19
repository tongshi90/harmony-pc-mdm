"""表格抽取：按 cell 几何识别合并格，并将同一文本回填到覆盖的所有网格单元。"""

from __future__ import annotations

from typing import Any

from app.rag.splitter.pdf.text_clean import clean_extracted_text

_EDGE_TOL = 3.0


def _cluster_edges(values: list[float], tol: float = _EDGE_TOL) -> list[float]:
    if not values:
        return []
    values = sorted(values)
    edges = [values[0]]
    for v in values[1:]:
        if abs(v - edges[-1]) > tol:
            edges.append(v)
    return edges


def _nearest_edge_index(edges: list[float], value: float) -> int:
    return min(range(len(edges)), key=lambda i: abs(edges[i] - value))


def _span_range(
    start_val: float,
    end_val: float,
    edges: list[float],
) -> tuple[int, int]:
    """返回覆盖 [start_val, end_val] 的网格下标区间 [i, j)（基于边线）。"""
    if len(edges) < 2:
        return 0, 0
    i = _nearest_edge_index(edges, start_val)
    j = _nearest_edge_index(edges, end_val)
    if j <= i:
        j = min(i + 1, len(edges) - 1)
    j = max(j, i + 1)
    j = min(j, len(edges) - 1)
    i = max(0, min(i, len(edges) - 2))
    return i, j


def _fallback_extract(table: Any) -> list[list[str]]:
    raw_rows = table.extract() or []
    return [
        [clean_extracted_text(c) for c in row]
        for row in raw_rows
        if isinstance(row, (list, tuple))
    ]


def _text_from_raw(
    raw: list[list[Any]],
    r0: int,
    r1: int,
    c0: int,
    c1: int,
) -> str:
    """在合并覆盖的原始格子里取第一个非空文本。"""
    for r in range(r0, r1):
        if r < 0 or r >= len(raw):
            continue
        row = raw[r]
        for c in range(c0, c1):
            if c < 0 or c >= len(row):
                continue
            text = clean_extracted_text(row[c])
            if text:
                return text
    return ""


def extract_table_matrix(table: Any) -> list[list[str]]:
    """抽取二维表，合并单元格同值展开到所有覆盖格。

    文本以 ``table.extract()`` 为准（避免 crop 串行）；
    合并范围用 ``table.cells`` 几何推算。
    """
    try:
        physical_cells = [c for c in (table.cells or []) if c is not None]
        if not physical_cells:
            return _fallback_extract(table)

        xs: list[float] = []
        ys: list[float] = []
        for x0, top, x1, bottom in physical_cells:
            xs.extend([float(x0), float(x1)])
            ys.extend([float(top), float(bottom)])
        x_edges = _cluster_edges(xs)
        y_edges = _cluster_edges(ys)
        n_cols = max(0, len(x_edges) - 1)
        n_rows = max(0, len(y_edges) - 1)
        if n_cols <= 0 or n_rows <= 0:
            return _fallback_extract(table)

        raw = table.extract() or []
        # 对齐行数：以几何网格为准
        grid: list[list[str]] = [["" for _ in range(n_cols)] for _ in range(n_rows)]

        for bbox in physical_cells:
            x0, top, x1, bottom = (
                float(bbox[0]),
                float(bbox[1]),
                float(bbox[2]),
                float(bbox[3]),
            )
            c0, c1 = _span_range(x0, x1, x_edges)
            r0, r1 = _span_range(top, bottom, y_edges)
            text = _text_from_raw(raw, r0, r1, c0, c1)
            for r in range(r0, r1):
                for c in range(c0, c1):
                    if 0 <= r < n_rows and 0 <= c < n_cols:
                        if text or not grid[r][c]:
                            grid[r][c] = text

        if not any(any(cell for cell in row) for row in grid):
            return _fallback_extract(table)
        return grid
    except Exception:
        return _fallback_extract(table)
