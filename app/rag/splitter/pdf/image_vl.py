"""图片 → 文本：调用多模态 Chat（可选）。

模型 / URL / Key / 超时一律读 ``app.config.settings``（见「在线模型」段）：
  - Key：``rag_siliconflow_api_key``（MDM_RAG_SILICONFLOW_API_KEY）
  - URL：``rag_vl_url``，空则回落 ``rag_chat_url``
  - 模型：``rag_vl_model``（MDM_RAG_VL_MODEL）
  - 超时 / max_tokens：``rag_vl_timeout`` / ``rag_vl_max_tokens``

无 Key 时：仍会尝试读本地 _vl_cache；都没有则保留空 text。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 本地实验默认开启；无 Key 且无缓存时自动跳过网络调用
ENABLE_IMAGE_VL = True

# 缓存文件名带版本；改 prompt/清洗策略/取图方式时递增，避免继续命中坏结果
CACHE_VERSION = "v6"
# 疑似没写完时自动再请求一次
RETRY_ON_INCOMPLETE = True

_VL_PROMPT = """你是企业规章制度 PDF 的插图转写器。用简体中文把图里的业务内容说清楚，供检索用。

写法：
1. 开头半行标明类型（表格/流程图/示意图/其它）即可
2. 用自然语言或「A → B」写清可见文字与关系；不要强行 Markdown 表格
3. 表格类：按「每一数据行」写全该行各列含义（例：协议采购、自行采购：采购主管等审核；集团采购经理终审；分管采购副总裁为/）。合并单元格按实际归属写
4. 流程图：按顺序写节点与分支条件，抄录原文
5. 只写内容；不写颜色/背景/边框/字体；禁止「图中无…」否定凑字
6. 必须覆盖图中全部能看清的数据行与关键单元格；禁止只写到某一行的冒号/顿号就停笔
7. 写完整再结束；不要重复同一句；不要为凑字数注水"""

_KEY_RESOLVED_FROM: str | None = None


def _settings():
    from app.config import settings

    return settings


def _api_key() -> str:
    """从 app.config 读取共用 API Key。"""
    global _KEY_RESOLVED_FROM
    key = (_settings().rag_siliconflow_api_key or "").strip()
    _KEY_RESOLVED_FROM = "app.config" if key else None
    return key


def _chat_url() -> str:
    """VL 接口 URL：优先 rag_vl_url，否则回落主 Chat URL（均来自 app.config）。"""
    s = _settings()
    return (s.rag_vl_url or "").strip() or (s.rag_chat_url or "").strip()


def _vl_model() -> str:
    return (_settings().rag_vl_model or "").strip()


def _vl_timeout() -> int:
    return int(_settings().rag_vl_timeout or 90) or 90


def _vl_max_tokens() -> int:
    return int(_settings().rag_vl_max_tokens or 1200) or 1200


def _mime_for_format(fmt: str) -> str:
    f = (fmt or "png").lower()
    if f in ("jpg", "jpeg"):
        return "image/jpeg"
    if f == "webp":
        return "image/webp"
    if f == "gif":
        return "image/gif"
    return "image/png"


def _cache_path(cache_dir: Path, content_hash: str) -> Path:
    return cache_dir / f"{content_hash}.{CACHE_VERSION}.txt"


def _read_cache(cache_dir: Path | None, content_hash: str) -> str:
    if cache_dir is None or not content_hash:
        return ""
    path = _cache_path(cache_dir, content_hash)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _sanitize_vl_text(text: str) -> str:
    """去掉否定凑字，并切断「整行反复复读」的退化输出。

    注意：表格转写里「采购员审核；」等短句会在多行合法重复，
    不能按分号短句去重，否则会把后续行误砍掉。
    """
    import re

    raw = (text or "").strip()
    if not raw:
        return ""

    # 去掉整行「图中无… / 未显示… / 无法判断…」否定填充
    lines: list[str] = []
    skip_line = re.compile(
        r"^(图中无|未显示|无法判断|图中未|没有任何|不存在).*"
    )
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            continue
        if skip_line.match(s):
            continue
        lines.append(s)
    if not lines:
        first = raw.splitlines()[0].strip()
        return first

    # 连续完全相同的行：只留一行（打循环时常见）
    deduped: list[str] = []
    for ln in lines:
        if deduped and deduped[-1] == ln:
            continue
        deduped.append(ln)

    # 仅当「很长的整行」非连续再次出现时才截断（防长段循环）
    # 短行/分号片段允许重复（表格多行同结构）
    kept: list[str] = []
    seen_long: set[str] = set()
    for ln in deduped:
        key = re.sub(r"\s+", "", ln)
        if len(key) >= 40 and key in seen_long:
            break
        if len(key) >= 40:
            seen_long.add(key)
        kept.append(ln)
    return "\n".join(kept).strip()


def _looks_incomplete(text: str) -> bool:
    """粗判模型是否写到一半就停了（冒号收尾、半截列表等）。"""
    import re

    s = (text or "").strip()
    if not s:
        return True
    # 以这些收尾通常还没写完该行
    if s.endswith(("：", ":", "、", "，", ",", "-", "→", "->")):
        return True
    # 「基建：采购员审核；」这类：最后一段过短且像刚起了个头
    last = s.splitlines()[-1].strip()
    if last.endswith(("：", ":")) and len(last) <= 40:
        return True
    # 以分号结尾，且最后一个「类别：…」片段明显偏短
    if last.endswith("；"):
        segs = [x for x in re.split(r"[；;]", last) if x.strip()]
        if segs and len(segs[-1].strip()) <= 12 and "：" in segs[-1]:
            # 例如只写到「基建：采购员审核」
            return True
    return False


def _call_vl_once(
    *,
    data_url: str,
    prompt: str,
    temperature: float = 0.1,
) -> tuple[str, str]:
    """返回 (raw_text, finish_reason)。失败则 ("", reason/error)。"""
    try:
        import requests
    except ImportError:
        logger.warning("[pdf-img] 缺少 requests，跳过 VL")
        return "", "no_requests"

    payload = {
        "model": _vl_model(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": _vl_max_tokens(),
        "temperature": temperature,
    }
    try:
        resp = requests.post(
            _chat_url(),
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload),
            timeout=_vl_timeout(),
        )
        if resp.status_code >= 400:
            logger.warning(
                "[pdf-img] VL HTTP %s: %s",
                resp.status_code,
                (resp.text or "")[:300],
            )
            return "", f"http_{resp.status_code}"
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return "", "no_choices"
        choice = choices[0] or {}
        finish = str(choice.get("finish_reason") or "")
        msg = choice.get("message") or {}
        return str(msg.get("content") or "").strip(), finish
    except Exception as exc:
        logger.warning("[pdf-img] VL 调用失败: %s", exc)
        return "", "exception"


def describe_image_bytes(
    image_bytes: bytes,
    *,
    fmt: str = "png",
    content_hash: str | None = None,
    cache_dir: Path | None = None,
) -> str:
    """单张图转写；优先读缓存，再调 VL；失败返回空串。"""
    if not ENABLE_IMAGE_VL:
        return ""

    digest = content_hash or hashlib.sha1(image_bytes).hexdigest()
    cached = _sanitize_vl_text(_read_cache(cache_dir, digest))
    # 旧缓存若明显半截，作废重跑
    if cached and not _looks_incomplete(cached):
        return cached

    key = _api_key()
    if not key:
        return cached  # 无 Key 时即便半截也只能用缓存

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)

    mime = _mime_for_format(fmt)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    raw, finish = _call_vl_once(data_url=data_url, prompt=_VL_PROMPT)
    text = _sanitize_vl_text(raw)
    if finish == "length":
        logger.warning("[pdf-img] VL finish_reason=length，输出可能被 max_tokens 截断")

    if (
        RETRY_ON_INCOMPLETE
        and (_looks_incomplete(text) or finish == "length")
    ):
        retry_prompt = (
            _VL_PROMPT
            + "\n\n上次输出疑似未写完。请重新完整转写本图，务必覆盖每一数据行的全部列，"
            "不要停在冒号后面。"
        )
        raw2, finish2 = _call_vl_once(
            data_url=data_url, prompt=retry_prompt, temperature=0.2
        )
        text2 = _sanitize_vl_text(raw2)
        if text2 and (
            not _looks_incomplete(text2)
            or len(text2) > len(text)
        ):
            text = text2
            finish = finish2

    if text and cache_dir is not None and not _looks_incomplete(text):
        _cache_path(cache_dir, digest).write_text(text, encoding="utf-8")
    elif text and cache_dir is not None:
        # 半截结果也落盘便于排查，但文件名加 incomplete 标记不覆盖正式缓存
        bad = cache_dir / f"{digest}.{CACHE_VERSION}.incomplete.txt"
        bad.write_text(text, encoding="utf-8")
        logger.warning("[pdf-img] VL 结果仍疑似不完整，未写入正式缓存")
    return text


def fill_image_texts(
    images: list[dict[str, Any]],
    *,
    cache_dir: Path | None = None,
) -> dict[str, int]:
    """批量为 image block 写 text；返回统计。"""
    stats = {
        "total": len(images),
        "ok": 0,
        "skip": 0,
        "fail": 0,
        "from_cache": 0,
        "from_api": 0,
    }
    if not ENABLE_IMAGE_VL:
        logger.debug("[pdf-img] VL 已关闭，跳过图转文 n=%s", len(images))
        stats["skip"] = len(images)
        return stats
    if not images:
        return stats

    key = _api_key()
    if key:
        logger.debug(
            "[pdf-img] VL 转写开始: n=%s model=%s key_from=%s",
            len(images),
            _vl_model(),
            _KEY_RESOLVED_FROM,
        )
    else:
        logger.debug(
            "[pdf-img] 未解析到 API Key，仅尝试本地 _vl_cache"
        )

    for i, img in enumerate(images, start=1):
        digest = str(img.get("content_hash") or "").strip()
        # 无 Key 时也先读缓存，避免「已识别过却仍显示待识别」
        cached = (
            _sanitize_vl_text(_read_cache(cache_dir, digest)) if digest else ""
        )
        # 半截缓存视为无效，走 API 重跑
        if cached and not _looks_incomplete(cached):
            img["text"] = cached
            stats["ok"] += 1
            stats["from_cache"] += 1
            continue

        if not key:
            img["text"] = cached if cached else ""
            stats["fail"] += 1
            continue

        data = img.get("image_bytes")
        if not data:
            path = img.get("image_path")
            if path and Path(path).is_file():
                data = Path(path).read_bytes()
        if not data:
            stats["fail"] += 1
            img["text"] = ""
            continue

        text = describe_image_bytes(
            data,
            fmt=str(img.get("format") or "png"),
            content_hash=digest or None,
            cache_dir=cache_dir,
        )
        if text:
            img["text"] = text
            stats["ok"] += 1
            stats["from_api"] += 1
        else:
            img["text"] = ""
            stats["fail"] += 1

    logger.info(
        "[pdf-img] VL 转写结束: ok=%s (cache=%s api=%s) fail=%s skip=%s",
        stats["ok"],
        stats["from_cache"],
        stats["from_api"],
        stats["fail"],
        stats["skip"],
    )
    return stats
