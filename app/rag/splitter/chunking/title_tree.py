"""目录处理 + 标题栈按标题开片 + 仅标题合并。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Section:
    """切分过程中的临时节。"""

    title_path: list[str] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)
    page: int | None = None
    chunk_type: str = "text"

    def append_text(self, text: str, *, page: int | None = None) -> None:
        t = (text or "").rstrip()
        if not t:
            return
        self.parts.append(t)
        if self.page is None and page is not None:
            self.page = page

    @property
    def text(self) -> str:
        return "\n".join(self.parts).strip()

    @property
    def section_title(self) -> str:
        return self.title_path[-1] if self.title_path else ""


def _normalize_ws(s: str) -> str:
    return "".join((s or "").split())


def _title_level(unit: dict[str, Any]) -> int:
    try:
        level = int(unit.get("level") or 1)
    except (TypeError, ValueError):
        level = 1
    return max(level, 1)


def _is_body_title(unit: dict[str, Any]) -> bool:
    return (
        unit.get("kind") == "line"
        and (unit.get("role") or "") == "title"
        and not unit.get("in_toc")
    )


def _flush_toc(toc_parts: list[str], toc_page: int | None, out: list[_Section]) -> None:
    if not toc_parts:
        return
    sec = _Section(title_path=["目录"], chunk_type="toc", page=toc_page)
    for p in toc_parts:
        sec.append_text(p)
    if sec.text:
        out.append(sec)


def _seal(current: _Section | None, out: list[_Section]) -> None:
    if current is None:
        return
    if not current.text:
        return
    out.append(current)


def split_units_by_title(units: list[dict[str, Any]]) -> list[_Section]:
    """按标题栈切分 unit 流，返回节列表（含可选 toc）。"""
    out: list[_Section] = []
    stack: list[tuple[int, str]] = []  # (level, title_text)
    current: _Section | None = None
    saw_body_title = False

    toc_parts: list[str] = []
    toc_page: int | None = None
    toc_flushed = False

    def ensure_preamble() -> _Section:
        nonlocal current
        if current is None:
            current = _Section(title_path=[], chunk_type="text")
        return current

    def open_section(title: str, level: int, *, page: int | None) -> None:
        nonlocal current, stack, saw_body_title
        saw_body_title = True
        # 弹出同级或更高级
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        path = [t for _, t in stack]
        current = _Section(title_path=path, chunk_type="text", page=page)
        current.append_text(title, page=page)

    for unit in units:
        kind = unit.get("kind")
        page = unit.get("page")

        # ---- 目录行：聚成至多一片 toc，不参与正文标题栈 ----
        if kind == "line" and unit.get("in_toc"):
            if not toc_flushed:
                text = (unit.get("text") or "").strip()
                if text:
                    toc_parts.append(text)
                    if toc_page is None and page is not None:
                        toc_page = page
            continue

        # 正文开始后第一次遇到非 toc 内容时，封存目录片
        if toc_parts and not toc_flushed:
            # 若当前还是前言阶段、且即将开标题/写正文，先把 toc 落盘
            # 但 toc 应插在前言之后、正文标题之前：若已有前言 current，先 seal 前言
            if current is not None and not saw_body_title and current.text:
                _seal(current, out)
                current = None
            _flush_toc(toc_parts, toc_page, out)
            toc_parts = []
            toc_flushed = True

        if _is_body_title(unit):
            title = (unit.get("text") or "").strip()
            if not title:
                continue
            # 封存上一节
            if current is not None:
                _seal(current, out)
                current = None
            elif toc_parts and not toc_flushed:
                _flush_toc(toc_parts, toc_page, out)
                toc_parts = []
                toc_flushed = True
            open_section(title, _title_level(unit), page=page)
            continue

        if kind == "line":
            text = (unit.get("text") or "").strip()
            if not text:
                continue
            ensure_preamble().append_text(text, page=page)
            continue

        if kind == "table":
            body = (unit.get("text") or "").strip()
            piece = f"【表格】\n{body}" if body else "【表格】"
            ensure_preamble().append_text(piece, page=page)
            continue

        if kind == "image":
            body = (unit.get("text") or "").strip()
            if body:
                piece = f"【图片】\n{body}"
            else:
                piece = "【图片】（无转写文本）"
            ensure_preamble().append_text(piece, page=page)
            continue

    # 收尾
    if toc_parts and not toc_flushed:
        if current is not None and not saw_body_title and current.text:
            _seal(current, out)
            current = None
        _flush_toc(toc_parts, toc_page, out)
        toc_parts = []
        toc_flushed = True

    _seal(current, out)
    return out


def _is_ancestor_path(parent: list[str], child: list[str]) -> bool:
    """child 的路径前缀是否等于 parent（下一节落在当前标题子树下）。"""
    if not parent:
        return False
    if len(child) < len(parent):
        return False
    return child[: len(parent)] == parent


def merge_title_only_sections(sections: list[_Section]) -> list[_Section]:
    """仅标题节与「其子树内」下一节合并；避免跨章误并。"""
    if not sections:
        return []
    result: list[_Section] = []
    i = 0
    n = len(sections)
    while i < n:
        cur = sections[i]
        if cur.chunk_type == "toc":
            result.append(cur)
            i += 1
            continue

        title = cur.section_title
        cur_norm = _normalize_ws(cur.text)
        title_norm = _normalize_ws(title)
        is_title_only = bool(title) and cur_norm == title_norm

        if is_title_only and i + 1 < n and sections[i + 1].chunk_type != "toc":
            nxt = sections[i + 1]
            # 仅当下一节仍在当前标题路径下（子级）时合并
            if _is_ancestor_path(cur.title_path, nxt.title_path):
                merged = _Section(
                    title_path=list(nxt.title_path),
                    chunk_type=nxt.chunk_type or "text",
                    page=cur.page if cur.page is not None else nxt.page,
                )
                if cur.text:
                    merged.append_text(cur.text, page=cur.page)
                if nxt.text and _normalize_ws(nxt.text) != cur_norm:
                    merged.append_text(nxt.text, page=nxt.page)
                result.append(merged)
                i += 2
                continue

        result.append(cur)
        i += 1
    return result
