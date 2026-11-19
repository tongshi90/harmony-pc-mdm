"""PDF 处理架子。

流程：
1. 外层判别是否扫描件（前几页文本量 < 阈值）→ 暂直接报错拒绝入库
2. 文本型 PDF：按页抽表+图+表/图外行 → 跨页投票去页眉页脚/页码/logo
   → 行与表/图按 top 组装
3. 跨页续表合并（图片不做跨页合并）
4. 保留图片可选 VL 转写为文本
5. 全文统计正文字号，标注疑似标题级别 / 备注（字号 > 加粗 > 正则）
6. 按标题树切分成 Chunk（共用 chunking；过长短治理后续另做）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.rag.splitter.base import DocumentSplitter
from app.rag.splitter.chunking import blocks_to_chunks
from app.rag.splitter.models import Chunk
from app.rag.splitter.pdf.header_footer import detect_header_footer_patterns, filter_page_lines
from app.rag.splitter.pdf.heading_detect import (
    annotate_document_blocks,
    chars_to_lines,
)
from app.rag.splitter.pdf.image_extract import (
    extract_page_images,
    filter_noise_images,
)
from app.rag.splitter.pdf.image_header_footer import (
    detect_fixed_image_patterns,
    filter_page_images,
)
from app.rag.splitter.pdf.image_vl import fill_image_texts
from app.rag.splitter.pdf.table_extract import extract_table_matrix
from app.rag.splitter.pdf.table_merge import format_rows, merge_cross_page_tables
from app.rag.splitter.pdf.text_clean import is_decorative_char

logger = logging.getLogger(__name__)


# ---------- 扫描件判别参数（可按实测调整）----------
SCAN_CHECK_PAGES = 3
SCAN_CHAR_THRESHOLD = 80


def _require_pdfplumber():
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError(
            "PDF 读取需要 pdfplumber，请在当前 venv 中安装: pip install pdfplumber"
        ) from exc
    return pdfplumber


def _point_in_bbox(x: float, y: float, bbox: tuple[float, float, float, float]) -> bool:
    x0, top, x1, bottom = bbox
    return x0 <= x <= x1 and top <= y <= bottom


def _item_sort_key(item: dict[str, Any]) -> tuple[float, float, int]:
    """阅读序：先上后下，再左后右；极近时 table > image > line。"""
    bbox = item.get("bbox")
    if not bbox:
        return (1e18, 1e18, 9)
    top = float(bbox[1])
    x0 = float(bbox[0])
    kind = item.get("kind")
    if kind == "table":
        kind_rank = 0
    elif kind == "image":
        kind_rank = 1
    else:
        kind_rank = 2
    return (top, x0, kind_rank)


def _flush_line_group(
    group: list[dict[str, Any]],
    *,
    page_no: int,
    page_height: float,
    page_width: float,
    text_index: int,
) -> dict[str, Any] | None:
    if not group:
        return None
    text = "\n".join(l["text"] for l in group if l.get("text"))
    x0 = min(float(l["bbox"][0]) for l in group)
    top = min(float(l["bbox"][1]) for l in group)
    x1 = max(float(l["bbox"][2]) for l in group)
    bottom = max(float(l["bbox"][3]) for l in group)
    return {
        "kind": "text",
        "page": page_no,
        "index": text_index,
        "bbox": (x0, top, x1, bottom),
        "page_height": page_height,
        "page_width": page_width,
        "lines": list(group),
        "text": text,
    }


def _assemble_blocks_by_reading_order(
    *,
    lines: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    images: list[dict[str, Any]] | None = None,
    page_no: int,
    page_height: float,
    page_width: float,
) -> list[dict[str, Any]]:
    """方案 A：行与表/图按垂直位置排队，连续行合成 text block，表/图插在中间。"""
    items: list[dict[str, Any]] = []
    for line in lines:
        bbox = line.get("bbox")
        if not bbox:
            continue
        items.append({"kind": "line", "bbox": bbox, "line": line})
    for table in tables:
        items.append({"kind": "table", "bbox": table.get("bbox"), "table": table})
    for image in images or []:
        items.append({"kind": "image", "bbox": image.get("bbox"), "image": image})

    items.sort(key=_item_sort_key)

    blocks: list[dict[str, Any]] = []
    line_group: list[dict[str, Any]] = []
    text_index = 0

    def flush() -> None:
        nonlocal text_index, line_group
        block = _flush_line_group(
            line_group,
            page_no=page_no,
            page_height=page_height,
            page_width=page_width,
            text_index=text_index,
        )
        line_group = []
        if block:
            blocks.append(block)
            text_index += 1

    for item in items:
        if item["kind"] == "line":
            line_group.append(item["line"])
        elif item["kind"] == "table":
            flush()
            blocks.append(item["table"])
        else:
            flush()
            blocks.append(item["image"])

    flush()
    return blocks


def _strip_image_bytes_for_blocks(blocks: list[dict[str, Any]]) -> None:
    """组装完成后去掉内存中的原图字节，避免后续打印/调试膨胀。"""
    for b in blocks:
        if b.get("kind") == "image":
            b.pop("image_bytes", None)


class PdfSplitter(DocumentSplitter):
    supported_suffixes = (".pdf",)

    def is_scanned_pdf(self, file_path: Path) -> bool:
        """前若干页可抽取文本合计低于阈值 → 视为扫描件。"""
        pdfplumber = _require_pdfplumber()
        total_chars = 0
        with pdfplumber.open(str(file_path)) as pdf:
            pages = pdf.pages[:SCAN_CHECK_PAGES]
            for page in pages:
                text = page.extract_text() or ""
                total_chars += len(text.strip())

        is_scanned = total_chars < SCAN_CHAR_THRESHOLD
        logger.info(
            "[pdf] 扫描件判别: pages=%s chars=%s threshold=%s => %s",
            SCAN_CHECK_PAGES,
            total_chars,
            SCAN_CHAR_THRESHOLD,
            "扫描件" if is_scanned else "文本型",
        )
        return is_scanned

    def _extract_page_raw(self, page, fitz_page=None) -> dict[str, Any]:
        """单页原始：表 + 图 + 表/图外文本行（尚未去眉脚）。"""
        table_bboxes: list[tuple[float, float, float, float]] = []
        image_bboxes: list[tuple[float, float, float, float]] = []
        page_height = float(page.height)
        page_width = float(page.width)
        page_no = page.page_number

        table_items: list[dict[str, Any]] = []
        try:
            found = page.find_tables() or []
        except Exception as exc:
            logger.warning("[pdf] 第 %s 页找表失败: %s", page_no, exc)
            found = []

        for idx, table in enumerate(found, start=1):
            bbox = tuple(float(x) for x in table.bbox)
            table_bboxes.append(bbox)
            try:
                rows = extract_table_matrix(table)
            except Exception as exc:
                logger.warning(
                    "[pdf] 第 %s 页表格#%s 抽取失败: %s", page_no, idx, exc
                )
                rows = []
            table_items.append(
                {
                    "kind": "table",
                    "page": page_no,
                    "index": idx,
                    "bbox": bbox,
                    "page_height": page_height,
                    "page_width": page_width,
                    "rows": rows,
                    "text": format_rows(rows),
                }
            )

        image_items: list[dict[str, Any]] = []
        if fitz_page is not None:
            try:
                image_items = extract_page_images(
                    fitz_page,
                    page_no=page_no,
                    page_width=page_width,
                    page_height=page_height,
                )
            except Exception as exc:
                logger.warning("[pdf] 第 %s 页抽图失败: %s", page_no, exc)
                image_items = []
            for img in image_items:
                bbox = img.get("bbox")
                if bbox:
                    image_bboxes.append(tuple(float(x) for x in bbox))

        try:
            chars = page.chars or []
        except Exception as exc:
            logger.warning("[pdf] 第 %s 页抽 chars 失败: %s", page_no, exc)
            chars = []

        skip_bboxes = table_bboxes + image_bboxes
        outside_chars: list[dict[str, Any]] = []
        for ch in chars:
            try:
                cx = (float(ch["x0"]) + float(ch["x1"])) / 2.0
                cy = (float(ch["top"]) + float(ch["bottom"])) / 2.0
            except (KeyError, TypeError, ValueError):
                continue
            if any(_point_in_bbox(cx, cy, b) for b in skip_bboxes):
                continue
            if is_decorative_char(ch.get("text") or "", ch.get("fontname")):
                continue
            outside_chars.append(ch)

        lines = chars_to_lines(outside_chars)
        return {
            "page": page_no,
            "page_height": page_height,
            "page_width": page_width,
            "tables": table_items,
            "images": image_items,
            "lines": lines,
        }

    def extract_page_blocks(self, page, fitz_page=None) -> list[dict[str, Any]]:
        """单页抽取（无跨页眉脚投票；完整链路请走 extract_document）。"""
        raw = self._extract_page_raw(page, fitz_page=fitz_page)
        kept_imgs, _ = filter_noise_images(raw["images"])
        return _assemble_blocks_by_reading_order(
            lines=raw["lines"],
            tables=raw["tables"],
            images=kept_imgs,
            page_no=raw["page"],
            page_height=raw["page_height"],
            page_width=raw["page_width"],
        )

    def extract_document(self, file_path: Path) -> list[dict[str, Any]]:
        """扫描件分流 → 按页抽取 → 去眉脚/页码/logo → 跨页续表 → VL → 标题标注。"""
        pdfplumber = _require_pdfplumber()
        try:
            import pymupdf
        except ImportError as exc:
            raise ImportError(
                "PDF 图片抽取需要 pymupdf，请在当前 venv 中安装: pip install pymupdf"
            ) from exc

        if self.is_scanned_pdf(file_path):
            msg = (
                f"暂不支持扫描版 PDF（可抽取文本过少）：{file_path.name}。"
                "请上传可选中复制文字的文本型 PDF，或先 OCR 后再上传。"
            )
            logger.warning("[pdf] reject scanned pdf: %s", file_path)
            raise ValueError(msg)

        raw_pages: list[dict[str, Any]] = []
        with pdfplumber.open(str(file_path)) as pdf, pymupdf.open(
            str(file_path)
        ) as doc:
            n = min(len(pdf.pages), doc.page_count)
            for i in range(n):
                raw_pages.append(
                    self._extract_page_raw(pdf.pages[i], fitz_page=doc[i])
                )

        # 小图/装饰条过滤（每页独立）
        noise_dropped = 0
        for raw in raw_pages:
            kept, dropped = filter_noise_images(raw.get("images") or [])
            noise_dropped += len(dropped)
            raw["images"] = kept
            raw["_dropped_noise"] = dropped

        # 文本眉脚 + 图片眉脚（logo）跨页投票
        hf_patterns = detect_header_footer_patterns(raw_pages)
        img_hf_patterns = detect_fixed_image_patterns(raw_pages)

        removed_total = 0
        logo_dropped = 0
        all_blocks: list[dict[str, Any]] = []
        kept_images_for_vl: list[dict[str, Any]] = []

        for raw in raw_pages:
            kept_lines, removed = filter_page_lines(
                raw["lines"],
                page_height=float(raw["page_height"]),
                patterns=hf_patterns,
            )
            removed_total += removed

            kept_imgs, dropped_logos = filter_page_images(
                raw.get("images") or [],
                patterns=img_hf_patterns,
            )
            logo_dropped += len(dropped_logos)
            kept_images_for_vl.extend(kept_imgs)

            all_blocks.extend(
                _assemble_blocks_by_reading_order(
                    lines=kept_lines,
                    tables=raw["tables"],
                    images=kept_imgs,
                    page_no=raw["page"],
                    page_height=raw["page_height"],
                    page_width=raw["page_width"],
                )
            )

        logger.debug(
            "[pdf] 眉脚/图片过滤: removed_lines=%s noise=%s logo=%s kept_images=%s",
            removed_total,
            noise_dropped,
            logo_dropped,
            len(kept_images_for_vl),
        )

        # VL 转写（内存中完成，不落盘；写回同一批 image dict）
        if kept_images_for_vl:
            fill_image_texts(kept_images_for_vl, cache_dir=None)

        merged = merge_cross_page_tables(all_blocks)
        _strip_image_bytes_for_blocks(merged)
        meta = annotate_document_blocks(merged)
        img_blocks = sum(1 for b in merged if b.get("kind") == "image")
        logger.debug(
            "[pdf] blocks=%s images=%s body_size=%s regex_titles=%s",
            len(merged),
            img_blocks,
            meta.get("body_size"),
            meta.get("regex_title_count"),
        )
        return merged

    def split(self, file_path: Path) -> list[Chunk]:
        blocks = self.extract_document(file_path)
        # 正文/annotated 校验改由 output JSON 查看，控制台不再打印全文
        return blocks_to_chunks(blocks, source="pdf")
