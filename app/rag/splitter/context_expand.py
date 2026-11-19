"""提问侧：按 Plan A / Plan B 回挂生成上下文。

Plan A（rule）：
- 章节因过长拆成多片（有 parent_id）→ 优先提交完整章节；
  子片现文拼接（编辑后即时生效），同父多命中只提交一次。
- 整章超过单块 token 上限 → 以命中片为中心截取局部窗。
- 未拆章的整节命中 → 原片提交（同样受单块上限约束）。

Plan B（plain）：
- 命中片 ± 前后邻域；相连区间合并；超单块上限同样居中截窗。

生成侧另有总预算：多块合计超限时按命中顺序保留，超出部分裁掉/截断。
参考依据仍用命中小片（本模块只改生成用文本）。
"""

from __future__ import annotations

from typing import Any

from app.rag.splitter.sidecar import join_texts_dedupe_overlap, load_chunk_sidecar


def _est_tokens(text: str) -> int:
    """粗估 token：与切分侧一致，中文偏多场景用字数/2。"""
    n = len(text or "")
    return max(1, n // 2) if n else 0


def _chars_for_tokens(tokens: int) -> int:
    return max(1, int(tokens) * 2)


def _budget_settings() -> tuple[int, int]:
    """返回 (单块上限, 总预算)；读配置失败时用默认。"""
    chunk_max = 2500
    total_max = 8000
    try:
        from app.config import settings

        chunk_max = int(settings.rag_gen_chunk_max_tokens or chunk_max)
        total_max = int(settings.rag_gen_total_max_tokens or total_max)
    except Exception:
        pass
    chunk_max = max(200, chunk_max)
    total_max = max(chunk_max, total_max)
    return chunk_max, total_max


def _window_around_anchor(full: str, anchor: str, max_tokens: int) -> str:
    """在 full 中以 anchor 为中心截取不超过 max_tokens 的窗口。"""
    full = (full or "").strip()
    anchor = (anchor or "").strip()
    if not full:
        return ""
    if max_tokens <= 0:
        return ""
    if _est_tokens(full) <= max_tokens:
        return full

    max_chars = _chars_for_tokens(max_tokens)
    idx = -1
    if anchor:
        idx = full.find(anchor)
        if idx < 0:
            for n in (min(120, len(anchor)), min(60, len(anchor)), 24):
                if n <= 0:
                    break
                idx = full.find(anchor[:n])
                if idx >= 0:
                    break

    if idx < 0:
        piece = full[:max_chars]
        return (piece.rstrip() + ("…" if len(full) > len(piece) else "")).strip()

    half = max_chars // 2
    start = max(0, idx - half)
    end = min(len(full), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    piece = full[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(full) else ""
    return f"{prefix}{piece}{suffix}".strip()


def _apply_chunk_cap(
    text: str,
    *,
    hit_text: str,
    max_tokens: int,
    expand_tag: str,
) -> tuple[str, str]:
    """单块超限则居中截窗；返回 (正文, expand 标记)。"""
    body = (text or "").strip()
    if not body:
        return "", expand_tag
    if _est_tokens(body) <= max_tokens:
        return body, expand_tag
    clipped = _window_around_anchor(body, hit_text, max_tokens)
    return clipped, f"{expand_tag}_capped"


def _doc_id_of(chunk: dict[str, Any]) -> str:
    return str(chunk.get("full_doc_id") or chunk.get("doc_id") or "").strip()


def _order_of(chunk: dict[str, Any]) -> int | None:
    order = chunk.get("chunk_order_index")
    if isinstance(order, int):
        return order
    cid = str(chunk.get("chunk_id") or chunk.get("id") or "")
    if "-sec_" in cid:
        try:
            return int(cid.rsplit("-sec_", 1)[-1])
        except ValueError:
            return None
    if "-chunk-" in cid:
        try:
            return int(cid.rsplit("-chunk-", 1)[-1])
        except ValueError:
            return None
    return None


def _sidecar_row(
    sidecar: dict[str, Any], order: int | None
) -> dict[str, Any] | None:
    if order is None:
        return None
    for row in sidecar.get("chunks") or []:
        if isinstance(row, dict) and row.get("order") == order:
            return row
    return None


def _parent_by_id(
    sidecar: dict[str, Any], parent_id: str | None
) -> dict[str, Any] | None:
    if not parent_id:
        return None
    for p in sidecar.get("parents") or []:
        if isinstance(p, dict) and str(p.get("parent_id") or "") == str(parent_id):
            return p
    return None


def _by_order_map(sidecar: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for c in sidecar.get("chunks") or []:
        if isinstance(c, dict) and isinstance(c.get("order"), int):
            out[int(c["order"])] = c
    return out


def _chapter_full_text(
    sidecar: dict[str, Any], parent_id: str
) -> str:
    """完整章节正文：优先按子片现文拼接（编辑后即时生效），再回退 parent.content。"""
    parent = _parent_by_id(sidecar, parent_id)
    by_order = _by_order_map(sidecar)
    child_orders = list((parent or {}).get("child_orders") or [])
    if not child_orders:
        kids = [
            c
            for c in (sidecar.get("chunks") or [])
            if isinstance(c, dict) and str(c.get("parent_id") or "") == str(parent_id)
        ]
        kids.sort(key=lambda r: int(r.get("order") or 0))
        texts = [str(k.get("text") or "") for k in kids]
    else:
        texts = [
            str((by_order.get(o) or {}).get("text") or "")
            for o in child_orders
            if isinstance(o, int)
        ]
    rebuilt = join_texts_dedupe_overlap(texts)
    if rebuilt:
        return rebuilt
    return ((parent or {}).get("content") or "").strip()


def _is_plan_b(row: dict[str, Any], sidecar: dict[str, Any]) -> bool:
    route = str(row.get("route") or sidecar.get("route") or "").upper()
    if route == "B":
        return True
    doc_type = str(row.get("doc_type") or "").lower()
    if doc_type == "plain":
        return True
    # 无标题路径且无父块 → 按 plain 邻域处理
    if not row.get("parent_id") and not (row.get("title_path") or []):
        return True
    return False


def _neighbor_orders(row: dict[str, Any], by_order: dict[int, dict[str, Any]]) -> list[int]:
    orders: list[int] = []
    for key in ("prev_order", "order", "next_order"):
        if key == "order":
            ov = row.get("order")
        else:
            ov = row.get(key)
        if isinstance(ov, int) and ov in by_order and ov not in orders:
            orders.append(ov)
    if not orders and isinstance(row.get("order"), int):
        orders = [int(row["order"])]
    return orders


def _merge_order_intervals(
    intervals: list[tuple[int, int, dict[str, Any]]],
) -> list[tuple[int, int, dict[str, Any]]]:
    """合并重叠或相邻的 order 区间；代表 item 取首次出现。"""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda x: (x[0], x[1]))
    merged: list[tuple[int, int, dict[str, Any]]] = [ordered[0]]
    for lo, hi, item in ordered[1:]:
        mlo, mhi, mitem = merged[-1]
        if lo <= mhi + 1:
            merged[-1] = (mlo, max(mhi, hi), mitem)
        else:
            merged.append((lo, hi, item))
    return merged


def _range_text(
    by_order: dict[int, dict[str, Any]],
    lo: int,
    hi: int,
    *,
    hit_overrides: dict[int, str] | None = None,
) -> str:
    overrides = hit_overrides or {}
    parts: list[str] = []
    for o in range(lo, hi + 1):
        if o in overrides and overrides[o].strip():
            parts.append(overrides[o])
            continue
        row = by_order.get(o)
        if not row:
            continue
        parts.append(str(row.get("text") or ""))
    return join_texts_dedupe_overlap(parts)


def _chunk_body(c: dict[str, Any]) -> str:
    return str(c.get("content") or c.get("text") or "").strip()


def _apply_total_budget(
    chunks: list[dict[str, Any]],
    *,
    total_max_tokens: int,
) -> list[dict[str, Any]]:
    """按命中顺序累加；超总预算则截断末块或丢弃后续块。"""
    if not chunks or total_max_tokens <= 0:
        return chunks

    out: list[dict[str, Any]] = []
    used = 0
    for c in chunks:
        body = _chunk_body(c)
        tok = _est_tokens(body) if body else 0
        if used >= total_max_tokens:
            break
        if used + tok <= total_max_tokens:
            out.append(c)
            used += tok
            continue
        remain = total_max_tokens - used
        if remain < 80:
            break
        clipped = dict(c)
        hit = body
        # 尽量保留本块已有命中感：用当前正文自身做锚点截窗
        clipped["content"] = _window_around_anchor(body, hit[:120], remain)
        tag = str(clipped.get("_expand") or "hit")
        clipped["_expand"] = f"{tag}_total_trim"
        out.append(clipped)
        break

    return out if out else chunks[:1]


def expand_chunks_for_generation(
    chunks: list[dict[str, Any]],
    *,
    max_context_tokens: int | None = None,
    max_total_tokens: int | None = None,
) -> list[dict[str, Any]]:
    """返回用于 LLM 生成的扩窗/合并切片副本；并施加单块/总预算。"""
    cfg_chunk, cfg_total = _budget_settings()
    chunk_max = max(200, int(max_context_tokens or cfg_chunk))
    total_max = max(chunk_max, int(max_total_tokens or cfg_total))

    if not chunks:
        return []

    # 预加载侧车
    sidecar_cache: dict[str, dict[str, Any] | None] = {}

    def _sidecar(doc_id: str) -> dict[str, Any] | None:
        if doc_id not in sidecar_cache:
            sidecar_cache[doc_id] = load_chunk_sidecar(doc_id) if doc_id else None
        return sidecar_cache[doc_id]

    # Plan B：按文档收集扩窗区间
    plan_b_intervals: dict[str, list[tuple[int, int, dict[str, Any]]]] = {}
    plan_b_hit_text: dict[str, dict[int, str]] = {}
    actions: list[tuple] = []
    used_a_parents: set[tuple[str, str]] = set()
    a_parent_payload: dict[tuple[str, str], dict[str, Any]] = {}

    for c in chunks:
        item = dict(c)
        doc_id = _doc_id_of(c)
        order = _order_of(c)
        hit_text = str(c.get("content") or c.get("text") or "")
        sidecar = _sidecar(doc_id)
        if not sidecar:
            body, tag = _apply_chunk_cap(
                hit_text, hit_text=hit_text, max_tokens=chunk_max, expand_tag="hit"
            )
            item["content"] = body
            item["_expand"] = tag
            actions.append(("raw", item))
            continue

        row = _sidecar_row(sidecar, order)
        if not row:
            body, tag = _apply_chunk_cap(
                hit_text, hit_text=hit_text, max_tokens=chunk_max, expand_tag="hit"
            )
            item["content"] = body
            item["_expand"] = tag
            actions.append(("raw", item))
            continue

        parent_id = row.get("parent_id")
        doc_type = str(row.get("doc_type") or "").lower()

        # ---- Plan A：过长拆章 → 完整章节（过大则居中截窗）----
        if doc_type == "rule" and parent_id:
            key = (doc_id, str(parent_id))
            if key in used_a_parents:
                continue
            used_a_parents.add(key)
            full = _chapter_full_text(sidecar, str(parent_id)) or hit_text
            body, tag = _apply_chunk_cap(
                full,
                hit_text=hit_text,
                max_tokens=chunk_max,
                expand_tag="plan_a_parent",
            )
            payload = dict(item)
            payload["content"] = body
            payload["_expand"] = tag
            payload["_parent_id"] = str(parent_id)
            a_parent_payload[key] = payload
            actions.append(("a_parent", key))
            continue

        # ---- Plan B：±邻域，稍后合并 ----
        if _is_plan_b(row, sidecar):
            by_order = _by_order_map(sidecar)
            orders = _neighbor_orders(row, by_order)
            if not orders:
                body, tag = _apply_chunk_cap(
                    hit_text, hit_text=hit_text, max_tokens=chunk_max, expand_tag="hit"
                )
                item["content"] = body
                item["_expand"] = tag
                actions.append(("raw", item))
                continue
            lo, hi = min(orders), max(orders)
            plan_b_intervals.setdefault(doc_id, []).append((lo, hi, item))
            if isinstance(order, int) and hit_text.strip():
                plan_b_hit_text.setdefault(doc_id, {})[order] = hit_text
            actions.append(("b", doc_id, order if isinstance(order, int) else lo))
            continue

        # ---- Plan A 整节未拆 / 其它：原片 ----
        body, tag = _apply_chunk_cap(
            hit_text, hit_text=hit_text, max_tokens=chunk_max, expand_tag="hit"
        )
        item["content"] = body
        item["_expand"] = tag
        actions.append(("raw", item))

    # 合并 Plan B 相连区间
    plan_b_merged: dict[str, list[tuple[int, int, dict[str, Any]]]] = {}
    plan_b_emitted: set[tuple[str, int, int]] = set()
    for doc_id, intervals in plan_b_intervals.items():
        plan_b_merged[doc_id] = _merge_order_intervals(intervals)

    def _emit_plan_b(doc_id: str, seed_order: int | None) -> dict[str, Any] | None:
        merged = plan_b_merged.get(doc_id) or []
        sidecar = _sidecar(doc_id)
        if not sidecar or not merged:
            return None
        by_order = _by_order_map(sidecar)
        for lo, hi, seed in merged:
            if seed_order is not None and not (lo <= seed_order <= hi):
                continue
            key = (doc_id, lo, hi)
            if key in plan_b_emitted:
                return None
            plan_b_emitted.add(key)
            text = _range_text(
                by_order,
                lo,
                hi,
                hit_overrides=plan_b_hit_text.get(doc_id),
            )
            hit_anchor = ""
            if isinstance(seed_order, int):
                hit_anchor = (plan_b_hit_text.get(doc_id) or {}).get(seed_order) or ""
            if not hit_anchor:
                hit_anchor = str(seed.get("content") or seed.get("text") or "")
            expand_base = "plan_b_merged" if hi > lo else "plan_b_neighbor"
            body, tag = _apply_chunk_cap(
                text or hit_anchor,
                hit_text=hit_anchor,
                max_tokens=chunk_max,
                expand_tag=expand_base,
            )
            out_item = dict(seed)
            out_item["content"] = body
            out_item["_expand"] = tag
            out_item["_order_range"] = [lo, hi]
            return out_item
        return None

    out: list[dict[str, Any]] = []
    for act in actions:
        kind = act[0]
        if kind == "raw":
            out.append(act[1])
        elif kind == "a_parent":
            payload = a_parent_payload.get(act[1])
            if payload:
                out.append(payload)
        elif kind == "b":
            doc_id, seed_order = act[1], act[2]
            emitted = _emit_plan_b(doc_id, seed_order)
            if emitted:
                out.append(emitted)

    if not out:
        out = list(chunks)

    return _apply_total_budget(out, total_max_tokens=total_max)
