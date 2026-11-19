"""章节/页分片后的尺寸治理：过短合 → 过长拆（overlap + parent）。"""

from __future__ import annotations

import re
from typing import Any

from app.rag.splitter.models import Chunk

# ---------- 参数（与方案初值一致）----------
MIN_CHUNK_TOKENS = 80
MAX_CHUNK_TOKENS = 1000
CHUNK_TOKEN_TARGET = 600
CHUNK_OVERLAP_RATIO = 0.15

_SENT_END_RE = re.compile(r"(?<=[。！？；.!?;])\s*")

# 最近一次治理产生的父块，供 main 打印（split 实验用）
_LAST_PARENTS: list[dict[str, Any]] = []


def estimate_tokens(text: str) -> int:
    """粗估 token：中文偏多场景用字数/2。"""
    n = len(text or "")
    return max(1, n // 2) if n else 0


def get_last_parents() -> list[dict[str, Any]]:
    return list(_LAST_PARENTS)


def _meta(c: Chunk) -> dict[str, Any]:
    if not isinstance(c.meta, dict):
        c.meta = {}
    return c.meta


def _set_token_len(c: Chunk) -> None:
    _meta(c)["token_len"] = estimate_tokens(c.text or "")


def _doc_type_for(c: Chunk) -> str:
    if c.chunk_type == "toc":
        return "toc"
    if c.title_path:
        return "rule"
    return "plain"


def _path_relation(a: list[str], b: list[str]) -> str:
    """路径关系：same / ancestor / sibling / none。

    sibling = 同父下的同级标题（如 第六章/第十八条 与 第六章/第十九条）；
    顶层章与章（路径长度 1 且标题不同）视为 none，避免跨章合并。
    """
    if a == b:
        return "same"
    if not a or not b:
        return "same" if (not a and not b) else "none"
    # 祖先-后代
    if len(a) < len(b) and b[: len(a)] == a:
        return "ancestor"
    if len(b) < len(a) and a[: len(b)] == b:
        return "ancestor"
    # 同父同级（至少要有共同父节点，禁止两个顶层章互并）
    if len(a) >= 2 and len(a) == len(b) and a[:-1] == b[:-1]:
        return "sibling"
    return "none"


def _can_merge_pair(left: Chunk, right: Chunk) -> bool:
    if left.chunk_type == "toc" or right.chunk_type == "toc":
        return False
    lt = int(_meta(left).get("token_len") or estimate_tokens(left.text))
    rt = int(_meta(right).get("token_len") or estimate_tokens(right.text))
    rel = _path_relation(list(left.title_path or []), list(right.title_path or []))
    if rel == "none":
        return False
    # 同级短节：两侧都必须过短，才并到同一父节下
    if rel == "sibling":
        return lt < MIN_CHUNK_TOKENS and rt < MIN_CHUNK_TOKENS
    # 同路径或祖先：至少一侧过短即可（例如仅标题父节并入子节）
    if lt >= MIN_CHUNK_TOKENS and rt >= MIN_CHUNK_TOKENS:
        return False
    return True


def _merge_two(left: Chunk, right: Chunk) -> Chunk:
    """合并两片：同级取共同父路径；两侧都短的祖先合并也收束到父路径。"""
    lp = list(left.title_path or [])
    rp = list(right.title_path or [])
    rel = _path_relation(lp, rp)
    lt = int(_meta(left).get("token_len") or estimate_tokens(left.text))
    rt = int(_meta(right).get("token_len") or estimate_tokens(right.text))
    both_short = lt < MIN_CHUNK_TOKENS and rt < MIN_CHUNK_TOKENS

    if rel == "sibling":
        title_path = lp[:-1]  # 共同父节
    elif rel == "ancestor" and both_short:
        # 短片链继续并入时，停在父路径，避免又落到某一个子标题上
        title_path = lp if len(lp) <= len(rp) else rp
    elif len(rp) >= len(lp):
        title_path = rp
    else:
        title_path = lp

    section_title = ""
    if title_path:
        section_title = title_path[-1]
    else:
        section_title = str(_meta(left).get("section_title") or "") or str(
            _meta(right).get("section_title") or ""
        )

    text_parts = [t for t in [(left.text or "").strip(), (right.text or "").strip()] if t]
    text = "\n".join(text_parts)
    page = left.page if left.page is not None else right.page
    chunk_type = left.chunk_type if left.chunk_type == right.chunk_type else "text"
    if left.chunk_type == "slide" or right.chunk_type == "slide":
        chunk_type = "slide"

    meta: dict[str, Any] = {
        "section_title": section_title,
        "doc_type": "rule" if title_path else "plain",
        "source": _meta(left).get("source") or _meta(right).get("source") or "",
    }
    # 保留 PPT 相关调试字段
    for key in ("slide_index", "has_notes", "shape_text_count"):
        if key in _meta(left) or key in _meta(right):
            meta[key] = _meta(right).get(key, _meta(left).get(key))

    out = Chunk(
        chunk_id=left.chunk_id,
        order=left.order,
        text=text,
        page=page,
        title_path=title_path,
        chunk_type=chunk_type,
        meta=meta,
    )
    _set_token_len(out)
    return out


def merge_short_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """过短片与同路径相邻片合并；toc 不参与。"""
    if not chunks:
        return []
    for c in chunks:
        _set_token_len(c)
        m = _meta(c)
        m.setdefault("doc_type", _doc_type_for(c))
        if c.chunk_type == "toc":
            m["skip_embed"] = True

    result: list[Chunk] = []
    i = 0
    n = len(chunks)
    while i < n:
        cur = chunks[i]
        if cur.chunk_type == "toc":
            result.append(cur)
            i += 1
            continue

        # 向右吞并过短相邻片
        while i + 1 < n:
            nxt = chunks[i + 1]
            if not _can_merge_pair(cur, nxt):
                break
            # 合并后若仍短，继续尝试
            cur = _merge_two(cur, nxt)
            i += 1
        result.append(cur)
        i += 1
    return result


def _split_paragraphs(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"\n\s*\n+", text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        return parts
    # 单段：按行
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) >= 2:
        return lines
    # 再按句
    sents = [s.strip() for s in _SENT_END_RE.split(text) if s.strip()]
    return sents if sents else [text]


def _pack_units_with_overlap(units: list[str], *, target: int, overlap_ratio: float) -> list[str]:
    """将文本单元拼成接近 target token 的窗，窗间保留 overlap。"""
    if not units:
        return []
    windows: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    overlap_tokens = max(1, int(target * overlap_ratio))

    def flush() -> str:
        return "\n".join(buf).strip()

    for u in units:
        ut = estimate_tokens(u)
        if buf and buf_tokens + ut > target:
            windows.append(flush())
            # 从尾部回溯构造 overlap 缓冲
            overlap_buf: list[str] = []
            ot = 0
            for piece in reversed(buf):
                pt = estimate_tokens(piece)
                if ot + pt > overlap_tokens and overlap_buf:
                    break
                overlap_buf.insert(0, piece)
                ot += pt
            buf = overlap_buf
            buf_tokens = estimate_tokens("\n".join(buf)) if buf else 0
        buf.append(u)
        buf_tokens += ut

    if buf:
        last = flush()
        if last and (not windows or last != windows[-1]):
            windows.append(last)
    return windows


def _hard_split_by_chars(text: str, *, target: int, overlap_ratio: float) -> list[str]:
    """单句仍超长时按字符硬切。"""
    # target tokens ≈ 2*chars under our estimator
    max_chars = max(50, target * 2)
    overlap_chars = max(10, int(max_chars * overlap_ratio))
    s = text or ""
    if len(s) <= max_chars:
        return [s] if s.strip() else []
    out: list[str] = []
    start = 0
    n = len(s)
    while start < n:
        end = min(n, start + max_chars)
        out.append(s[start:end].strip())
        if end >= n:
            break
        start = max(start + 1, end - overlap_chars)
    return [x for x in out if x]


def split_text_to_windows(
    text: str,
    *,
    target: int = CHUNK_TOKEN_TARGET,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_ratio: float = CHUNK_OVERLAP_RATIO,
) -> list[str]:
    """将任意长文本按段/行/句装箱为窗（供路径 A 二次切与路径 B 复用）。"""
    units = _split_paragraphs(text or "")
    windows = _pack_units_with_overlap(
        units, target=target, overlap_ratio=overlap_ratio
    )
    final: list[str] = []
    for w in windows:
        if estimate_tokens(w) <= max_tokens:
            final.append(w)
        else:
            final.extend(
                _hard_split_by_chars(
                    w, target=target, overlap_ratio=overlap_ratio
                )
            )
    return [x for x in final if (x or "").strip()]


def split_long_chunk(chunk: Chunk) -> tuple[list[Chunk], dict[str, Any] | None]:
    """超长片二次切；返回子片列表与可选父块记录。"""
    _set_token_len(chunk)
    tok = int(_meta(chunk).get("token_len") or 0)
    if tok <= MAX_CHUNK_TOKENS:
        _meta(chunk).setdefault("doc_type", _doc_type_for(chunk))
        _meta(chunk)["parent_id"] = None
        return [chunk], None

    units = _split_paragraphs(chunk.text or "")
    windows = _pack_units_with_overlap(
        units, target=CHUNK_TOKEN_TARGET, overlap_ratio=CHUNK_OVERLAP_RATIO
    )
    # 仍有单窗过长则硬切
    final_windows: list[str] = []
    for w in windows:
        if estimate_tokens(w) <= MAX_CHUNK_TOKENS:
            final_windows.append(w)
        else:
            final_windows.extend(
                _hard_split_by_chars(
                    w, target=CHUNK_TOKEN_TARGET, overlap_ratio=CHUNK_OVERLAP_RATIO
                )
            )
    if not final_windows:
        _meta(chunk)["parent_id"] = None
        return [chunk], None

    # 仅一片则无需父块
    if len(final_windows) == 1 and final_windows[0].strip() == (chunk.text or "").strip():
        _meta(chunk)["parent_id"] = None
        return [chunk], None

    parent_id = f"parent_{chunk.chunk_id}"
    has_path = bool(chunk.title_path)
    doc_type = "rule" if has_path else "plain"
    parent: dict[str, Any] | None = None
    child_ids: list[str] = []

    children: list[Chunk] = []
    for i, w in enumerate(final_windows):
        cid = f"{chunk.chunk_id}_p{i}"
        child_ids.append(cid)
        meta = dict(_meta(chunk))
        meta["section_title"] = _meta(chunk).get("section_title") or (
            chunk.title_path[-1] if chunk.title_path else ""
        )
        meta["doc_type"] = doc_type
        meta["source"] = _meta(chunk).get("source") or ""
        if has_path:
            meta["parent_id"] = parent_id
        else:
            # plain：不建父块，只靠前后链
            meta["parent_id"] = None
        child = Chunk(
            chunk_id=cid,
            order=chunk.order,  # 稍后统一重排
            text=w,
            page=chunk.page,
            title_path=list(chunk.title_path or []),
            chunk_type=chunk.chunk_type or "text",
            meta=meta,
        )
        _set_token_len(child)
        children.append(child)

    if has_path:
        parent = {
            "parent_id": parent_id,
            "content": chunk.text,
            "child_ids": child_ids,
            "token_len": tok,
            "title_path": list(chunk.title_path or []),
            "section_title": _meta(chunk).get("section_title") or "",
        }
    return children, parent


def split_long_chunks(chunks: list[Chunk]) -> tuple[list[Chunk], list[dict[str, Any]]]:
    out: list[Chunk] = []
    parents: list[dict[str, Any]] = []
    for c in chunks:
        if c.chunk_type == "toc":
            _meta(c)["parent_id"] = None
            _meta(c)["doc_type"] = "toc"
            _meta(c)["skip_embed"] = True
            _set_token_len(c)
            out.append(c)
            continue
        kids, parent = split_long_chunk(c)
        out.extend(kids)
        if parent:
            parents.append(parent)
    return out, parents


def _reindex_and_link(chunks: list[Chunk]) -> list[Chunk]:
    """重算 order / chunk_id 并写前后链。"""
    result: list[Chunk] = []
    for i, c in enumerate(chunks):
        c.chunk_id = f"sec_{i}"
        c.order = i
        _set_token_len(c)
        m = _meta(c)
        m.setdefault("doc_type", _doc_type_for(c))
        result.append(c)

    for i, c in enumerate(result):
        m = _meta(c)
        m["prev_id"] = result[i - 1].chunk_id if i > 0 else None
        m["next_id"] = result[i + 1].chunk_id if i + 1 < len(result) else None
        if "parent_id" not in m:
            m["parent_id"] = None
    return result


def govern_chunks(chunks: list[Chunk]) -> tuple[list[Chunk], list[dict[str, Any]]]:
    """过短合 → 过长拆 → 重排与前后链。"""
    global _LAST_PARENTS
    if not chunks:
        _LAST_PARENTS = []
        return [], []

    merged = merge_short_chunks(chunks)
    split, parents = split_long_chunks(merged)
    final = _reindex_and_link(split)

    # 父块 child_ids 与重排后 id 对齐：按 title_path+内容匹配较难，
    # 改为按顺序：拆分时 child 的 parent_id 已写好；重排后更新 parent 内 child_ids
    id_by_parent: dict[str, list[str]] = {}
    for c in final:
        pid = _meta(c).get("parent_id")
        if pid:
            id_by_parent.setdefault(str(pid), []).append(c.chunk_id)
    for p in parents:
        pid = str(p.get("parent_id") or "")
        if pid in id_by_parent:
            p["child_ids"] = id_by_parent[pid]

    _LAST_PARENTS = parents
    return final, parents
