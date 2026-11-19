"""Word 结构化处理（对齐 PDF blocks 契约）。

流程（P0 + P1）：
1. 仅解析 .docx（.doc 经 msdoc2docx 先转 .docx）
2. 只遍历 body（页眉页脚自然不进入）
3. 按文档序：段落 / 表格 / 段内图 → text / table / image blocks
4. 页眉页脚图 hash 用于过滤正文 logo；小图噪声过滤
5. 表格矩阵文本；图片走与 PDF 同一套 VL
6. 标注：字号/加粗/正则 + 样式标题优先覆盖
7. 同款 annotated 打印；按标题树切 Chunk（共用 chunking）
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from app.rag.splitter.base import DocumentSplitter
from app.rag.splitter.chunking import blocks_to_chunks
from app.rag.splitter.models import Chunk
from app.rag.splitter.pdf.heading_detect import (
    annotate_document_blocks,
    assign_title_levels_for_blocks,
)
from app.rag.splitter.pdf.image_vl import fill_image_texts
from app.rag.splitter.word.image_extract import (
    build_image_block,
    collect_header_footer_image_hashes,
    iter_image_rids_in_element,
)
from app.rag.splitter.word.paragraph import paragraph_to_line
from app.rag.splitter.word.table_extract import table_to_block

logger = logging.getLogger(__name__)


_PAGE_LIKE_RE = re.compile(
    r"^(第\s*\d+\s*页|\d+\s*/\s*\d+|page\s*\d+)$",
    re.IGNORECASE,
)


def _require_docx():
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise ImportError(
            "Word 解析需要 python-docx，请在当前 venv 中安装: pip install python-docx"
        ) from exc
    return Document, qn, Table, Paragraph


def _iter_body_blocks(doc: Any) -> Iterable[tuple[str, Any]]:
    """按 body 子节点顺序产出 ('p'|'tbl', 对象)。"""
    Document, qn, Table, Paragraph = _require_docx()
    del Document
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield "p", Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield "tbl", Table(child, doc)


def _flush_lines(
    lines: list[dict[str, Any]],
    *,
    text_index: int,
) -> dict[str, Any] | None:
    if not lines:
        return None
    text = "\n".join(l.get("text") or "" for l in lines if l.get("text"))
    return {
        "kind": "text",
        "page": None,
        "index": text_index,
        "bbox": None,
        "lines": list(lines),
        "text": text,
    }


def _strip_image_bytes(blocks: list[dict[str, Any]]) -> None:
    for b in blocks:
        if b.get("kind") == "image":
            b.pop("image_bytes", None)


def apply_style_titles(blocks: list[dict[str, Any]]) -> int:
    """样式标题优先：覆盖字号/正则结果。返回覆盖条数。"""
    n = 0
    for b in blocks:
        if b.get("kind") != "text":
            continue
        for line in b.get("lines") or []:
            if not line.get("is_heading_style"):
                continue
            level = int(line.get("style_level") or 1)
            level = max(level, 1)
            prev = line.get("title_via")
            line["role"] = "title"
            line["level"] = level
            line["title_via"] = (
                f"style+{prev}" if prev and "style" not in str(prev) else "style"
            )
            n += 1
    return n


def filter_repeated_short_lines(
    blocks: list[dict[str, Any]],
    *,
    min_hits: int = 3,
    max_chars: int = 40,
) -> tuple[list[dict[str, Any]], int]:
    """正文中反复出现的短句（伪眉脚）弱过滤。"""
    counter: Counter[str] = Counter()
    for b in blocks:
        if b.get("kind") != "text":
            continue
        for line in b.get("lines") or []:
            t = (line.get("text") or "").strip()
            if not t or len(t) > max_chars:
                continue
            if line.get("is_heading_style"):
                continue
            counter[t] += 1

    drop_texts = {t for t, c in counter.items() if c >= min_hits}
    if not drop_texts and not any(
        _PAGE_LIKE_RE.match((t or "").replace(" ", "")) for t in counter
    ):
        return blocks, 0

    removed = 0
    out: list[dict[str, Any]] = []
    for b in blocks:
        if b.get("kind") != "text":
            out.append(b)
            continue
        kept_lines: list[dict[str, Any]] = []
        for line in b.get("lines") or []:
            t = (line.get("text") or "").strip()
            compact = re.sub(r"\s+", "", t)
            if t in drop_texts or _PAGE_LIKE_RE.match(compact or ""):
                removed += 1
                continue
            kept_lines.append(line)
        if not kept_lines:
            continue
        nb = dict(b)
        nb["lines"] = kept_lines
        nb["text"] = "\n".join(l.get("text") or "" for l in kept_lines)
        out.append(nb)
    return out, removed


class WordSplitter(DocumentSplitter):
    supported_suffixes = (".docx", ".doc")

    def extract_document(self, file_path: Path) -> list[dict[str, Any]]:
        Document, qn, Table, Paragraph = _require_docx()
        del qn, Table, Paragraph

        work_path = file_path
        if file_path.suffix.lower() == ".doc":
            # 与业务侧一致：msdoc2docx 先转 docx 再解析（不改写源 .doc）
            try:
                from app.rag.office_convert import convert_doc_to_docx
            except Exception:
                # split 实验目录可能未把仓库根加入 path
                import sys

                root = Path(__file__).resolve().parents[2]
                if str(root) not in sys.path:
                    sys.path.insert(0, str(root))
                from app.rag.office_convert import convert_doc_to_docx

            work_path = convert_doc_to_docx(
                file_path, dest=file_path.with_suffix(".docx")
            )
            logger.info(
                "[word] 已将 .doc 转为 .docx（msdoc2docx）: %s", work_path.name
            )

        doc = Document(str(work_path))
        hf_hashes = collect_header_footer_image_hashes(doc)
        logger.debug(
            "[word] 页眉页脚图片指纹: %s（正文同 hash 将丢弃）", len(hf_hashes)
        )

        blocks: list[dict[str, Any]] = []
        line_buf: list[dict[str, Any]] = []
        text_index = 0
        table_index = 0
        image_index = 0
        kept_images: list[dict[str, Any]] = []
        seen_image_hashes: set[str] = set()
        noise_dropped = 0
        logo_dropped = 0
        dup_dropped = 0

        def flush_text() -> None:
            nonlocal text_index, line_buf
            block = _flush_lines(line_buf, text_index=text_index)
            line_buf = []
            if block:
                blocks.append(block)
                text_index += 1

        def emit_image_from_rid(rid: str, *, source: str) -> None:
            nonlocal image_index, noise_dropped, logo_dropped, dup_dropped
            image_index += 1
            img = build_image_block(doc, rid, index=image_index, source=source)
            if not img:
                return
            digest = str(img.get("content_hash") or "")
            # DrawingML + VML 常指向同一张图，按内容去重
            if digest and digest in seen_image_hashes:
                dup_dropped += 1
                return
            if digest and digest in hf_hashes:
                img["drop_reason"] = "header_footer_logo"
                logo_dropped += 1
                if digest:
                    seen_image_hashes.add(digest)
                return
            if img.get("drop_reason"):
                noise_dropped += 1
                if digest:
                    seen_image_hashes.add(digest)
                return
            # EMF/WMF：不送 VL（无可靠 PIL）
            fmt = str(img.get("format") or "").lower()
            if fmt in ("emf", "wmf"):
                noise_dropped += 1
                if digest:
                    seen_image_hashes.add(digest)
                return
            flush_text()
            blocks.append(img)
            kept_images.append(img)
            if digest:
                seen_image_hashes.add(digest)

        for kind, obj in _iter_body_blocks(doc):
            if kind == "p":
                # 段内图按 XML 出现顺序：先文本行，再图（同段图跟在段落后）
                line = paragraph_to_line(obj)
                if line:
                    line_buf.append(line)
                for rid in iter_image_rids_in_element(obj._element):
                    emit_image_from_rid(rid, source="paragraph")
            else:
                flush_text()
                table_index += 1
                tblock = table_to_block(obj, index=table_index)
                if tblock:
                    blocks.append(tblock)
                # 表内嵌图：挂在表后
                for rid in iter_image_rids_in_element(obj._tbl):
                    emit_image_from_rid(rid, source="table")

        flush_text()

        blocks, repeated_removed = filter_repeated_short_lines(blocks)
        logger.debug(
            "[word] 过滤: repeated_lines=%s noise=%s logo=%s dup=%s kept_images=%s",
            repeated_removed,
            noise_dropped,
            logo_dropped,
            dup_dropped,
            len(kept_images),
        )
        if kept_images:
            fill_image_texts(kept_images, cache_dir=None)

        _strip_image_bytes(blocks)
        meta = annotate_document_blocks(blocks)
        style_n = apply_style_titles(blocks)
        meta["style_title_count"] = style_n
        # 样式覆盖后再统一定级（样式优先）
        level_meta = assign_title_levels_for_blocks(blocks)
        meta["title_level_assign"] = level_meta

        img_n = sum(1 for b in blocks if b.get("kind") == "image")
        tbl_n = sum(1 for b in blocks if b.get("kind") == "table")
        logger.debug(
            "[word] blocks=%s tables=%s images=%s style_titles=%s regex_titles=%s",
            len(blocks),
            tbl_n,
            img_n,
            style_n,
            meta.get("regex_title_count"),
        )
        return blocks

    def split(self, file_path: Path) -> list[Chunk]:
        blocks = self.extract_document(file_path)
        # 正文/annotated 校验改由 output JSON 查看，控制台不再打印全文
        return blocks_to_chunks(blocks, source="word")
