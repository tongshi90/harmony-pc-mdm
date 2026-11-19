"""页眉页脚固定图片（企业 logo 等）跨页投票过滤。

与文本眉脚同范式：
1. 只看页顶/页底位置带
2. 指纹 = band + 量化 bbox + 内容 hash
3. 跨页高复现 → 视为版式装饰，删除，不参与解析 / VL
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.rag.splitter.pdf.header_footer import BAND_RATIO, _enough_hits


# 归一化 bbox 量化网格（相对页宽/页高）
BBOX_GRID = 0.02


def _band_of_bbox(
    bbox: tuple[float, float, float, float] | list[float],
    page_height: float,
) -> str | None:
    if not bbox or page_height <= 0:
        return None
    top = float(bbox[1])
    bottom = float(bbox[3])
    mid = (top + bottom) / 2.0
    if mid <= page_height * BAND_RATIO:
        return "top"
    if mid >= page_height * (1.0 - BAND_RATIO):
        return "bottom"
    return None


def _quant_bbox_key(
    bbox: tuple[float, float, float, float] | list[float],
    *,
    page_width: float,
    page_height: float,
) -> tuple[int, int, int, int]:
    pw = max(float(page_width), 1.0)
    ph = max(float(page_height), 1.0)
    x0, top, x1, bottom = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    return (
        int(round((x0 / pw) / BBOX_GRID)),
        int(round((top / ph) / BBOX_GRID)),
        int(round((x1 / pw) / BBOX_GRID)),
        int(round((bottom / ph) / BBOX_GRID)),
    )


def _fingerprint(image: dict[str, Any]) -> tuple[Any, ...] | None:
    bbox = image.get("bbox")
    page_height = float(image.get("page_height") or 0)
    page_width = float(image.get("page_width") or 0)
    if not bbox or page_height <= 0 or page_width <= 0:
        return None
    band = _band_of_bbox(bbox, page_height)
    if not band:
        return None
    digest = str(image.get("content_hash") or "").strip()
    if not digest:
        return None
    q = _quant_bbox_key(bbox, page_width=page_width, page_height=page_height)
    return (band, q, digest)


def detect_fixed_image_patterns(
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    """从多页 images 投票得到固定眉脚图模式。

    pages 项需含: page, page_height, page_width, images: [...]
    """
    total_pages = len(pages)
    # fingerprint -> set(page)
    hits: dict[tuple[Any, ...], set[int]] = defaultdict(set)
    samples: dict[tuple[Any, ...], dict[str, Any]] = {}

    for page in pages:
        page_no = int(page.get("page") or 0)
        seen_on_page: set[tuple[Any, ...]] = set()
        for img in page.get("images") or []:
            fp = _fingerprint(img)
            if fp is None or fp in seen_on_page:
                continue
            seen_on_page.add(fp)
            hits[fp].add(page_no)
            samples.setdefault(
                fp,
                {
                    "band": fp[0],
                    "quant_bbox": fp[1],
                    "content_hash": fp[2],
                    "sample_page": page_no,
                    "sample_index": img.get("index"),
                    "sample_size": f"{img.get('width')}x{img.get('height')}",
                },
            )

    fixed_images: list[dict[str, Any]] = []
    for fp, pageset in hits.items():
        if _enough_hits(len(pageset), total_pages):
            info = dict(samples.get(fp) or {})
            info["hits"] = len(pageset)
            info["fingerprint"] = {
                "band": fp[0],
                "quant_bbox": fp[1],
                "content_hash": fp[2],
            }
            fixed_images.append(info)

    return {
        "total_pages": total_pages,
        "fixed_images": fixed_images,
    }


def is_header_footer_image(
    image: dict[str, Any],
    *,
    patterns: dict[str, Any],
) -> bool:
    """单张图是否应作为眉脚 logo 丢弃。"""
    fp = _fingerprint(image)
    if fp is None:
        return False
    for item in patterns.get("fixed_images") or []:
        f = item.get("fingerprint") or {}
        if (
            f.get("band") == fp[0]
            and tuple(f.get("quant_bbox") or ()) == fp[1]
            and f.get("content_hash") == fp[2]
        ):
            return True
    return False


def filter_page_images(
    images: list[dict[str, Any]],
    *,
    patterns: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """过滤一页中的眉脚固定图，返回 (保留, 丢弃)。"""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for img in images:
        if is_header_footer_image(img, patterns=patterns):
            dropped.append({**img, "drop_reason": "header_footer_logo"})
        else:
            kept.append(img)
    return kept, dropped
