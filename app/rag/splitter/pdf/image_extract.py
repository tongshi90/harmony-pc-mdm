"""PDF 图片抽取：按页取出显示实例（bbox + 页面渲染图），并做小图/装饰条过滤。

坐标系与 pdfplumber 一致：原点在左上，y 向下增大（top/bottom）。

重要：不少制度 PDF 里表格被「整表显示」，但 ``extract_image(xref)`` 得到的
内嵌 JPEG 往往只有表头、下半截发黑；页面实际像素（pixmap clip）才完整。
因此送 VL / 落盘一律用 **按 bbox 裁切的页面渲染图**，不用内嵌流原图。
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 相对页面积过小 → 装饰/图标
MIN_AREA_RATIO = 0.004
# 绝对下限（点^2），避免大页上仍放过极小图
MIN_AREA_ABS = 40.0 * 40.0
# 极扁/极瘦 → 分割线类
MAX_ASPECT_RATIO = 18.0
# 页面渲染倍率（清晰度 / 体积折中）
RENDER_SCALE = 2.0
# 裁切外扩（点），避免框线被切掉
CLIP_PAD = 1.5


def _require_pymupdf():
    try:
        import pymupdf
    except ImportError as exc:
        raise ImportError(
            "PDF 图片抽取需要 pymupdf，请在当前 venv 中安装: pip install pymupdf"
        ) from exc
    return pymupdf


def _fitz_rect_to_plumber_bbox(
    rect: Any, page_height: float
) -> tuple[float, float, float, float]:
    """PyMuPDF get_image_rects → pdfplumber (x0, top, x1, bottom)。

    实测 ``Page.get_image_rects`` 返回值与 pdfplumber.images 的
    top/bottom 一致（原点在左上，y 向下），无需再按 PDF 底原点翻转。
    """
    del page_height
    x0 = float(rect.x0)
    x1 = float(rect.x1)
    top = float(rect.y0)
    bottom = float(rect.y1)
    if top > bottom:
        top, bottom = bottom, top
    return (x0, top, x1, bottom)


def _content_hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _render_clip_png(
    fitz_page: Any,
    rect: Any,
    *,
    page_width: float,
    page_height: float,
) -> tuple[bytes, int, int] | None:
    """按显示矩形渲染页面裁切 PNG，返回 (bytes, w, h)。"""
    pymupdf = _require_pymupdf()
    try:
        x0 = max(0.0, float(rect.x0) - CLIP_PAD)
        y0 = max(0.0, float(rect.y0) - CLIP_PAD)
        x1 = min(float(page_width), float(rect.x1) + CLIP_PAD)
        y1 = min(float(page_height), float(rect.y1) + CLIP_PAD)
        if x1 - x0 < 2 or y1 - y0 < 2:
            return None
        clip = pymupdf.Rect(x0, y0, x1, y1)
        pix = fitz_page.get_pixmap(
            matrix=pymupdf.Matrix(RENDER_SCALE, RENDER_SCALE),
            clip=clip,
            alpha=False,
        )
        return pix.tobytes("png"), int(pix.width), int(pix.height)
    except Exception as exc:
        logger.warning("[pdf-img] 页面裁切渲染失败: %s", exc)
        return None


def is_noise_image(
    bbox: tuple[float, float, float, float],
    *,
    page_width: float,
    page_height: float,
    min_area_ratio: float = MIN_AREA_RATIO,
    min_area_abs: float = MIN_AREA_ABS,
    max_aspect: float = MAX_ASPECT_RATIO,
) -> tuple[bool, str]:
    """启发式：过小或极扁/极瘦视为装饰，不进正文解析。"""
    x0, top, x1, bottom = bbox
    w = max(0.0, float(x1) - float(x0))
    h = max(0.0, float(bottom) - float(top))
    area = w * h
    page_area = max(float(page_width) * float(page_height), 1.0)
    if area < min_area_abs or area / page_area < min_area_ratio:
        return True, "too_small"
    if h > 0 and w / h > max_aspect:
        return True, "too_wide"
    if w > 0 and h / w > max_aspect:
        return True, "too_tall"
    return False, ""


def extract_page_images(
    fitz_page: Any,
    *,
    page_no: int,
    page_width: float,
    page_height: float,
) -> list[dict[str, Any]]:
    """抽取单页全部图片显示实例（尚未做眉脚/噪声过滤）。

    ``image_bytes`` 为页面渲染 PNG（所见即所得），不是内嵌 xref 原图。
    """
    pymupdf = _require_pymupdf()
    items: list[dict[str, Any]] = []
    try:
        image_list = fitz_page.get_images(full=True) or []
    except Exception as exc:
        logger.warning("[pdf-img] 第 %s 页 get_images 失败: %s", page_no, exc)
        return []

    idx = 0
    for img_info in image_list:
        xref = int(img_info[0])
        try:
            rects = fitz_page.get_image_rects(xref) or []
        except Exception:
            rects = []
        if not rects:
            continue

        for rect in rects:
            if isinstance(rect, pymupdf.Rect) and rect.is_empty:
                continue
            bbox = _fitz_rect_to_plumber_bbox(rect, page_height)
            rendered = _render_clip_png(
                fitz_page,
                rect,
                page_width=page_width,
                page_height=page_height,
            )
            if not rendered:
                logger.warning(
                    "[pdf-img] 第 %s 页 xref=%s 渲染失败，跳过该显示实例",
                    page_no,
                    xref,
                )
                continue
            image_bytes, pixel_w, pixel_h = rendered
            idx += 1
            items.append(
                {
                    "kind": "image",
                    "page": page_no,
                    "index": idx,
                    "bbox": bbox,
                    "page_height": float(page_height),
                    "page_width": float(page_width),
                    "image_bytes": image_bytes,
                    "width": pixel_w,
                    "height": pixel_h,
                    "format": "png",
                    "content_hash": _content_hash(image_bytes),
                    "xref": xref,
                    "source": "page_render",
                    "text": "",
                    "drop_reason": "",
                }
            )
    return items


def filter_noise_images(
    images: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按面积/长宽比过滤装饰图。返回 (保留, 丢弃)。"""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for img in images:
        bbox = img.get("bbox")
        if not bbox:
            img = {**img, "drop_reason": "no_bbox"}
            dropped.append(img)
            continue
        noisy, reason = is_noise_image(
            tuple(float(x) for x in bbox),
            page_width=float(img.get("page_width") or 1),
            page_height=float(img.get("page_height") or 1),
        )
        if noisy:
            img = {**img, "drop_reason": reason}
            dropped.append(img)
        else:
            kept.append(img)
    return kept, dropped


def save_image_bytes(
    image: dict[str, Any],
    dest_dir: Path,
    *,
    prefix: str = "img",
) -> Path | None:
    """把图片字节落到 dest_dir，并写回 image['image_path']。"""
    data = image.get("image_bytes")
    if not data:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    page = int(image.get("page") or 0)
    index = int(image.get("index") or 0)
    digest = str(image.get("content_hash") or "x")[:10]
    fmt = str(image.get("format") or "png").lower()
    if fmt == "jpeg":
        fmt = "jpg"
    name = f"{prefix}_p{page}_{index}_{digest}.{fmt}"
    path = dest_dir / name
    path.write_bytes(data)
    image["image_path"] = str(path)
    return path
