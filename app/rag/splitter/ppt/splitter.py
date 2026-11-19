"""PPT 切分实现（独立实验代码，可整文件替换算法）。

当前基线（P0）：
- .pptx：一页（幻灯片）一片；标题占位符 / 正文文本 / 表格 / 备注
- .ppt：经 ppt2pptx 先转 .pptx，再走同一路径（不改写源 .ppt）
- 无章节树；有标题占位则记录，无则不猜
- 分片结果由 main.py 统一按「标题路径 / 分片标题 / 内容」打印

依赖：python-pptx、ppt2pptx（见 requirements.txt）。

P1（图片，尚未实现；下一阶段在此扩展）：
- 在阅读序中识别 Picture 类 shape，按 top/left 插入本页内容流
- 过滤过小图 / 多页重复 logo（content hash）
- 复用 pdf.image_vl.fill_image_texts 做 VL 转写（内存、不落盘）
- 拼装时使用【图片】前缀，与 PDF/Word 校验观感对齐
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.rag.splitter.base import DocumentSplitter
from app.rag.splitter.chunking import govern_chunks
from app.rag.splitter.chunking.route import clear_last_route_decision
from app.rag.splitter.models import Chunk

logger = logging.getLogger(__name__)


class PptSplitter(DocumentSplitter):
    supported_suffixes = (".pptx", ".ppt")

    def split(self, file_path: Path) -> list[Chunk]:
        work_path = file_path
        if file_path.suffix.lower() == ".ppt":
            # 与 Word .doc 一致：先转再解析（不改写源文件）
            try:
                from app.rag.office_convert import convert_ppt_to_pptx
            except Exception:
                import sys

                root = Path(__file__).resolve().parents[2]
                if str(root) not in sys.path:
                    sys.path.insert(0, str(root))
                from app.rag.office_convert import convert_ppt_to_pptx

            work_path = convert_ppt_to_pptx(
                file_path, dest=file_path.with_suffix(".pptx")
            )
            logger.info(
                "[ppt] 已将 .ppt 转为 .pptx（ppt2pptx）: %s", work_path.name
            )

        return self._split_pptx(work_path)

    def _split_pptx(self, file_path: Path) -> list[Chunk]:
        try:
            from pptx import Presentation
            from pptx.enum.shapes import MSO_SHAPE_TYPE
        except ImportError as exc:
            raise ImportError(
                "PPT 切分需要 python-pptx，请先安装: pip install python-pptx"
            ) from exc

        prs = Presentation(str(file_path))
        chunks: list[Chunk] = []
        order = 0
        total = len(prs.slides)

        for slide_idx, slide in enumerate(prs.slides, start=1):
            titles: list[str] = []
            bodies: list[str] = []

            for shape in slide.shapes:
                if not getattr(shape, "has_text_frame", False):
                    continue
                text = (shape.text_frame.text or "").strip()
                if not text:
                    continue
                # 标题占位符优先；无占位符不猜测标题
                try:
                    if shape.is_placeholder and shape.placeholder_format.idx == 0:
                        titles.append(text)
                        continue
                except (AttributeError, ValueError):
                    pass
                bodies.append(text)

            for shape in slide.shapes:
                if shape.shape_type != MSO_SHAPE_TYPE.TABLE:
                    continue
                table = shape.table
                rows: list[str] = []
                for row in table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        rows.append(" | ".join(cells))
                if rows:
                    bodies.append("【表格】\n" + "\n".join(rows))

            # P1：此处按阅读序插入图片 shape → 过滤 → VL →【图片】文本（见模块头注释）

            notes = ""
            try:
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                    notes = (slide.notes_slide.notes_text_frame.text or "").strip()
            except (AttributeError, ValueError):
                notes = ""

            title = titles[0] if titles else ""
            title_path = [title] if title else []

            # Chunk 文本：标题 + 正文 + 备注（完整，供后续入库；标识便于 LLM 区分）
            chunk_parts: list[str] = []
            if title:
                chunk_parts.append(f"【标题】\n{title}")
            if bodies:
                chunk_parts.append("【正文】\n" + "\n\n".join(bodies))
            if notes:
                chunk_parts.append(f"【备注】\n{notes}")
            chunk_text = "\n\n".join(chunk_parts).strip()

            chunks.append(
                Chunk(
                    chunk_id=f"ppt_s{slide_idx}",
                    order=order,
                    text=chunk_text,
                    page=slide_idx,
                    title_path=title_path,
                    chunk_type="slide",
                    meta={
                        "section_title": title,
                        "source": "ppt",
                        "slide_index": slide_idx,
                        "has_notes": bool(notes),
                        "shape_text_count": len(bodies),
                        # P1 可补充 image_count 等
                    },
                )
            )
            order += 1

        # PPT 按页切，不走标题质量分流 B
        clear_last_route_decision()
        governed, _parents = govern_chunks(chunks)
        for c in governed:
            if isinstance(c.meta, dict):
                c.meta.setdefault("route", "ppt")
        return governed
