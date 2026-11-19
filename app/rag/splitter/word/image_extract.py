"""从 Word 正文抽取嵌入图片（跳过页眉页脚）。"""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 像素面积 / 长宽比噪声阈值（无页坐标系时用像素）
MIN_PIXEL_AREA = 40 * 40
MAX_ASPECT = 18.0

_A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
_R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
_VML_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"
_R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _content_hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _image_size(data: bytes) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            return int(im.width), int(im.height)
    except Exception:
        return 0, 0


def is_noise_image_pixels(width: int, height: int) -> tuple[bool, str]:
    w, h = max(0, int(width)), max(0, int(height))
    area = w * h
    if area < MIN_PIXEL_AREA:
        return True, "too_small"
    if h > 0 and w / h > MAX_ASPECT:
        return True, "too_wide"
    if w > 0 and h / w > MAX_ASPECT:
        return True, "too_tall"
    return False, ""


def _part_bytes(doc: Any, rid: str) -> tuple[bytes, str] | None:
    if not rid:
        return None
    try:
        part = doc.part.related_parts.get(rid)
    except Exception:
        part = None
    if part is None:
        return None
    blob = getattr(part, "blob", None)
    if not blob:
        return None
    ctype = str(getattr(part, "content_type", "") or "")
    ext = "png"
    if "jpeg" in ctype or "jpg" in ctype:
        ext = "jpg"
    elif "png" in ctype:
        ext = "png"
    elif "gif" in ctype:
        ext = "gif"
    elif "emf" in ctype:
        ext = "emf"
    elif "wmf" in ctype:
        ext = "wmf"
    return bytes(blob), ext


def iter_image_rids_in_element(element: Any) -> list[str]:
    """从段落/单元格 XML 中收集图片 relationship id（顺序保留）。"""
    rids: list[str] = []
    seen: set[str] = set()
    for blip in element.iter(_A_BLIP):
        rid = blip.get(_R_EMBED) or ""
        if rid and rid not in seen:
            seen.add(rid)
            rids.append(rid)
    for node in element.iter(_VML_IMAGEDATA):
        rid = node.get(_R_ID) or node.get("id") or ""
        if rid and rid not in seen:
            seen.add(rid)
            rids.append(rid)
    return rids


def build_image_block(
    doc: Any,
    rid: str,
    *,
    index: int,
    source: str = "body",
) -> dict[str, Any] | None:
    got = _part_bytes(doc, rid)
    if not got:
        return None
    data, fmt = got
    # EMF/WMF 暂不送 VL（缺少可靠解码）；仍可落盘占位
    w, h = _image_size(data) if fmt in ("png", "jpg", "jpeg", "gif", "webp") else (0, 0)
    noisy, reason = is_noise_image_pixels(w, h) if w and h else (False, "")
    # 无法读尺寸的矢量图：不按噪声丢，留给后续；过小点阵图丢弃
    if noisy:
        return {
            "kind": "image",
            "page": None,
            "index": index,
            "bbox": None,
            "image_bytes": data,
            "width": w,
            "height": h,
            "format": fmt,
            "content_hash": _content_hash(data),
            "rid": rid,
            "source": source,
            "text": "",
            "drop_reason": reason,
        }
    return {
        "kind": "image",
        "page": None,
        "index": index,
        "bbox": None,
        "image_bytes": data,
        "width": w,
        "height": h,
        "format": fmt,
        "content_hash": _content_hash(data),
        "rid": rid,
        "source": source,
        "text": "",
        "drop_reason": "",
    }


def collect_header_footer_image_hashes(doc: Any) -> set[str]:
    """页眉页脚中的图片 hash，用于正文去 logo。"""
    hashes: set[str] = set()
    for section in doc.sections:
        for hf in (section.header, section.footer):
            try:
                element = hf._element
            except Exception:
                continue
            for rid in iter_image_rids_in_element(element):
                got = _part_bytes(doc, rid)
                if got:
                    hashes.add(_content_hash(got[0]))
    return hashes


def save_image_bytes(
    image: dict[str, Any],
    dest_dir: Path,
    *,
    prefix: str = "img",
) -> Path | None:
    data = image.get("image_bytes")
    if not data:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    index = int(image.get("index") or 0)
    digest = str(image.get("content_hash") or "x")[:10]
    fmt = str(image.get("format") or "png").lower()
    if fmt == "jpeg":
        fmt = "jpg"
    path = dest_dir / f"{prefix}_{index}_{digest}.{fmt}"
    path.write_bytes(data)
    image["image_path"] = str(path)
    return path
