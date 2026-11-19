"""Office 格式转换（纯 Python 依赖，不调用本机 Office / LibreOffice）。

- ``.doc`` → ``.docx``：msdoc2docx（import doc2docx）
- ``.ppt`` → ``.pptx``：ppt2pptx
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("mdm.rag.convert")


def convert_doc_to_docx(
    src: str | Path,
    *,
    dest: str | Path | None = None,
) -> Path:
    """将 ``.doc`` 转为 ``.docx``。

    - 使用 ``msdoc2docx``（import ``doc2docx``），不依赖本机 Word / LibreOffice
    - 默认输出到源文件同目录、同主文件名的 ``.docx``
    - 不改写源 ``.doc``
    - 返回生成的 ``.docx`` 路径
    """
    src_path = Path(src)
    if not src_path.is_file():
        raise FileNotFoundError(f"源文件不存在: {src_path}")
    if src_path.suffix.lower() != ".doc":
        raise ValueError(f"仅支持 .doc 转换，收到: {src_path.suffix}")

    out_path = Path(dest) if dest else src_path.with_suffix(".docx")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from doc2docx import convert
    except ImportError as exc:
        raise ImportError(
            "缺少 msdoc2docx（import doc2docx），无法将 .doc 转为 .docx。"
            "请执行: pip install msdoc2docx"
        ) from exc

    try:
        result = convert(src_path, out_path)
    except Exception as exc:
        raise RuntimeError(f".doc 转 .docx 失败: {src_path.name}: {exc}") from exc

    produced = Path(getattr(result, "output_path", out_path) or out_path)
    if not produced.is_file():
        raise RuntimeError(
            f".doc 转 .docx 失败: {src_path.name}（未生成文件 {produced}）"
        )

    logger.info("已转换 .doc → .docx: %s → %s", src_path, produced)
    return produced


def convert_ppt_to_pptx(
    src: str | Path,
    *,
    dest: str | Path | None = None,
) -> Path:
    """将 ``.ppt`` 转为 ``.pptx``。

    - 使用 ``ppt2pptx``，不依赖本机 PowerPoint / LibreOffice
    - 默认输出到源文件同目录、同主文件名的 ``.pptx``
    - 不改写源 ``.ppt``
    - 返回生成的 ``.pptx`` 路径
    """
    src_path = Path(src)
    if not src_path.is_file():
        raise FileNotFoundError(f"源文件不存在: {src_path}")
    if src_path.suffix.lower() != ".ppt":
        raise ValueError(f"仅支持 .ppt 转换，收到: {src_path.suffix}")

    out_path = Path(dest) if dest else src_path.with_suffix(".pptx")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from ppt2pptx import convert
    except ImportError as exc:
        raise ImportError(
            "缺少 ppt2pptx，无法将 .ppt 转为 .pptx。"
            "请执行: pip install ppt2pptx"
        ) from exc

    try:
        result = convert(src_path, out_path)
    except Exception as exc:
        raise RuntimeError(f".ppt 转 .pptx 失败: {src_path.name}: {exc}") from exc

    produced = Path(getattr(result, "output_path", out_path) or out_path)
    if not produced.is_file():
        raise RuntimeError(
            f".ppt 转 .pptx 失败: {src_path.name}（未生成文件 {produced}）"
        )

    logger.info("已转换 .ppt → .pptx: %s → %s", src_path, produced)
    return produced
