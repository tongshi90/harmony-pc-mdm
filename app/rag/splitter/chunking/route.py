"""标题试切后的路径 A/B 分流判定。

护栏 P1/P2/P3 → 强制 A；硬规则 H1/H2/H3 → B；软分 ≥ 阈值 → B；否则 A。
参数见本模块常量与 ``get_route_params()``。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.rag.splitter.chunking.size_govern import (
    CHUNK_OVERLAP_RATIO,
    CHUNK_TOKEN_TARGET,
    MAX_CHUNK_TOKENS,
    MIN_CHUNK_TOKENS,
    estimate_tokens,
)
from app.rag.splitter.models import Chunk

# ---------- 判定参数（与说明文档初值一致）----------
LONG_CHAPTER_TOKENS = 1800
FULLTEXT_LONG_TOKENS = 1000
SHORT_DOC_TOKENS = 800
R_TITLE_ONLY_SOFT = 0.45
R_SHORT_SOFT = 0.45
R_LONG_SOFT = 0.65
R_TITLE_ONLY_HARD = 0.50
R_SHORT_HARD = 0.50
R_LONG_HARD = 0.70
R_TITLE_ONLY_H3 = 0.30
SCORE_B_THRESHOLD = 2
TITLE_DENSITY_MAX = 1.0 / 80.0
N_MIN_SOFT = 6
N_MIN_HARD_H2 = 8
N_MIN_HARD_H3 = 5
N_MIN_DENSE = 15


def get_route_params() -> dict[str, Any]:
    """A/B 判定与切分用到的阈值参数（便于控制台/JSON 核对）。"""
    return {
        "judge": {
            "MIN_CHUNK_TOKENS": MIN_CHUNK_TOKENS,
            "LONG_CHAPTER_TOKENS": LONG_CHAPTER_TOKENS,
            "FULLTEXT_LONG_TOKENS": FULLTEXT_LONG_TOKENS,
            "SHORT_DOC_TOKENS": SHORT_DOC_TOKENS,
            "R_TITLE_ONLY_SOFT": R_TITLE_ONLY_SOFT,
            "R_SHORT_SOFT": R_SHORT_SOFT,
            "R_LONG_SOFT": R_LONG_SOFT,
            "R_TITLE_ONLY_HARD": R_TITLE_ONLY_HARD,
            "R_SHORT_HARD": R_SHORT_HARD,
            "R_LONG_HARD": R_LONG_HARD,
            "R_TITLE_ONLY_H3": R_TITLE_ONLY_H3,
            "SCORE_B_THRESHOLD": SCORE_B_THRESHOLD,
            "TITLE_DENSITY_MAX": TITLE_DENSITY_MAX,
            "N_MIN_SOFT": N_MIN_SOFT,
            "N_MIN_HARD_H2": N_MIN_HARD_H2,
            "N_MIN_HARD_H3": N_MIN_HARD_H3,
            "N_MIN_DENSE": N_MIN_DENSE,
            "force_A_guards": {
                "P3": "T_all < SHORT_DOC_TOKENS",
                "P1": "N>=3 and title_only_ratio<0.25 and short_ratio<0.30 and long_ratio<0.40",
                "P2": "long_ratio<0.40 and title_only_ratio<0.35",
            },
            "hard_B": {
                "H1": "n_title<=1 and T_all>=FULLTEXT_LONG_TOKENS",
                "H2": "N>=N_MIN_HARD_H2 and title_only_ratio>=R_TITLE_ONLY_HARD and short_ratio>=R_SHORT_HARD",
                "H3": "N>=N_MIN_HARD_H3 and long_ratio>=R_LONG_HARD and title_only_ratio>=R_TITLE_ONLY_H3",
            },
            "soft_B": {
                "S1": "N>=N_MIN_SOFT and title_only_ratio>=R_TITLE_ONLY_SOFT",
                "S2": "N>=N_MIN_SOFT and short_ratio>=R_SHORT_SOFT",
                "S3": "N>=4 and long_ratio>=R_LONG_SOFT",
                "S4": "N>=N_MIN_DENSE and title_density>=TITLE_DENSITY_MAX",
                "S5": "level_jump_rate>=0.40",
                "enter_B_if": "soft_score >= SCORE_B_THRESHOLD",
            },
        },
        "split": {
            "MIN_CHUNK_TOKENS": MIN_CHUNK_TOKENS,
            "MAX_CHUNK_TOKENS": MAX_CHUNK_TOKENS,
            "CHUNK_TOKEN_TARGET": CHUNK_TOKEN_TARGET,
            "CHUNK_OVERLAP_RATIO": CHUNK_OVERLAP_RATIO,
            "token_estimate": "max(1, len(text)//2)",
        },
    }


@dataclass
class RouteDecision:
    route: str  # "A" | "B"
    blocked_by: str | None = None
    hard_hit: str | None = None
    soft_score: int = 0
    soft_hits: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_LAST_ROUTE: RouteDecision | None = None


def get_last_route_decision() -> RouteDecision | None:
    return _LAST_ROUTE


def clear_last_route_decision() -> None:
    global _LAST_ROUTE
    _LAST_ROUTE = None


def _normalize_ws(s: str) -> str:
    return "".join((s or "").split())


def is_title_only_chunk(chunk: Chunk) -> bool:
    """仅标题无正文（假切开）。"""
    body = (chunk.text or "").strip()
    meta = chunk.meta if isinstance(chunk.meta, dict) else {}
    title = str(meta.get("section_title") or "").strip()
    if not title and chunk.title_path:
        title = str(chunk.title_path[-1] or "").strip()

    n_body = _normalize_ws(body)
    n_title = _normalize_ws(title)
    tok = estimate_tokens(body)

    if n_title and n_body == n_title:
        return True
    if n_title and n_body.startswith(n_title):
        rest = body
        # 去掉首次出现的标题行再估剩余
        idx = body.find(title) if title else -1
        if idx >= 0:
            rest = (body[:idx] + body[idx + len(title) :]).strip()
        if estimate_tokens(rest) < 20:
            return True
    if chunk.title_path and tok < 20 and len([ln for ln in body.splitlines() if ln.strip()]) <= 2:
        return True
    return False


def count_body_titles_from_blocks(blocks: list[dict[str, Any]] | None) -> int | None:
    """统计标注阶段正文标题行数；无 blocks 时返回 None。"""
    if not blocks:
        return None
    n = 0
    for b in blocks:
        if b.get("kind") != "text":
            continue
        for line in b.get("lines") or []:
            if (line.get("role") or "") != "title":
                continue
            if line.get("in_toc"):
                continue
            if not (line.get("text") or "").strip():
                continue
            n += 1
    return n


def _level_jump_rate_from_blocks(blocks: list[dict[str, Any]] | None) -> float | None:
    if not blocks:
        return None
    levels: list[int] = []
    for b in blocks:
        if b.get("kind") != "text":
            continue
        for line in b.get("lines") or []:
            if (line.get("role") or "") != "title" or line.get("in_toc"):
                continue
            try:
                lv = int(line.get("level") or 1)
            except (TypeError, ValueError):
                lv = 1
            levels.append(max(lv, 1))
    if len(levels) < 2:
        return 0.0
    jumps = 0
    pairs = 0
    for i in range(1, len(levels)):
        pairs += 1
        if abs(levels[i] - levels[i - 1]) >= 2:
            jumps += 1
    return jumps / pairs if pairs else 0.0


def compute_metrics(
    chunks: list[Chunk],
    *,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """对试切结果计算分流指标（去掉 toc）。"""
    sample = [c for c in chunks if c.chunk_type != "toc"]
    full_text_parts = [(c.text or "").strip() for c in chunks if (c.text or "").strip()]
    full_text = "\n\n".join(full_text_parts)
    t_all = estimate_tokens(full_text)

    if not sample:
        sample_virtual = Chunk(
            chunk_id="virtual",
            order=0,
            text=full_text,
            title_path=[],
            chunk_type="text",
            meta={"section_title": ""},
        )
        sample = [sample_virtual]

    n = len(sample)
    n_title_only = 0
    n_short = 0
    n_long = 0
    for c in sample:
        tok = estimate_tokens(c.text or "")
        if is_title_only_chunk(c):
            n_title_only += 1
        if tok < MIN_CHUNK_TOKENS:
            n_short += 1
        if tok > LONG_CHAPTER_TOKENS:
            n_long += 1

    n_title = count_body_titles_from_blocks(blocks)
    if n_title is None:
        n_title = sum(1 for c in sample if c.title_path)

    title_density = (n_title / t_all) if t_all > 0 else 0.0
    level_jump = _level_jump_rate_from_blocks(blocks)

    return {
        "N": n,
        "T_all": t_all,
        "n_title": int(n_title),
        "title_only_ratio": n_title_only / n if n else 0.0,
        "short_ratio": n_short / n if n else 0.0,
        "long_ratio": n_long / n if n else 0.0,
        "title_density": title_density,
        "level_jump_rate": level_jump,
        "full_text": full_text,
    }


def hit_force_a(m: dict[str, Any]) -> tuple[bool, str | None]:
    """禁止降级护栏：命中则强制 A。"""
    t_all = int(m.get("T_all") or 0)
    n = int(m.get("N") or 0)
    title_only_ratio = float(m.get("title_only_ratio") or 0)
    short_ratio = float(m.get("short_ratio") or 0)
    long_ratio = float(m.get("long_ratio") or 0)

    if t_all < SHORT_DOC_TOKENS:
        return True, "P3"
    if (
        n >= 3
        and title_only_ratio < 0.25
        and short_ratio < 0.30
        and long_ratio < 0.40
    ):
        return True, "P1"
    if long_ratio < 0.40 and title_only_ratio < 0.35:
        return True, "P2"
    return False, None


def hit_hard_b(m: dict[str, Any]) -> tuple[bool, str | None]:
    n = int(m.get("N") or 0)
    t_all = int(m.get("T_all") or 0)
    n_title = int(m.get("n_title") or 0)
    title_only_ratio = float(m.get("title_only_ratio") or 0)
    short_ratio = float(m.get("short_ratio") or 0)
    long_ratio = float(m.get("long_ratio") or 0)

    if n_title <= 1 and t_all >= FULLTEXT_LONG_TOKENS:
        return True, "H1"
    if (
        n >= N_MIN_HARD_H2
        and title_only_ratio >= R_TITLE_ONLY_HARD
        and short_ratio >= R_SHORT_HARD
    ):
        return True, "H2"
    if (
        n >= N_MIN_HARD_H3
        and long_ratio >= R_LONG_HARD
        and title_only_ratio >= R_TITLE_ONLY_H3
    ):
        return True, "H3"
    return False, None


def soft_score(m: dict[str, Any]) -> tuple[int, list[str]]:
    n = int(m.get("N") or 0)
    title_only_ratio = float(m.get("title_only_ratio") or 0)
    short_ratio = float(m.get("short_ratio") or 0)
    long_ratio = float(m.get("long_ratio") or 0)
    title_density = float(m.get("title_density") or 0)
    level_jump = m.get("level_jump_rate")

    score = 0
    hits: list[str] = []
    if n >= N_MIN_SOFT and title_only_ratio >= R_TITLE_ONLY_SOFT:
        score += 1
        hits.append("S1")
    if n >= N_MIN_SOFT and short_ratio >= R_SHORT_SOFT:
        score += 1
        hits.append("S2")
    if n >= 4 and long_ratio >= R_LONG_SOFT:
        score += 1
        hits.append("S3")
    if n >= N_MIN_DENSE and title_density >= TITLE_DENSITY_MAX:
        score += 1
        hits.append("S4")
    if level_jump is not None and float(level_jump) >= 0.40:
        score += 1
        hits.append("S5")
    return score, hits


def decide_route(
    trial_chunks: list[Chunk],
    *,
    blocks: list[dict[str, Any]] | None = None,
) -> RouteDecision:
    """根据试切结果决定走 A 或 B。"""
    global _LAST_ROUTE
    m = compute_metrics(trial_chunks, blocks=blocks)
    # full_text 很大，决策对象里只留摘要字段
    metrics_log = {k: v for k, v in m.items() if k != "full_text"}
    for key in (
        "title_only_ratio",
        "short_ratio",
        "long_ratio",
        "title_density",
        "level_jump_rate",
    ):
        if metrics_log.get(key) is not None:
            metrics_log[key] = round(float(metrics_log[key]), 4)

    forced, why = hit_force_a(m)
    if forced:
        decision = RouteDecision(
            route="A",
            blocked_by=why,
            metrics=metrics_log,
        )
        _LAST_ROUTE = decision
        return decision

    hard, why_h = hit_hard_b(m)
    if hard:
        decision = RouteDecision(
            route="B",
            hard_hit=why_h,
            metrics=metrics_log,
        )
        _LAST_ROUTE = decision
        return decision

    score, hits = soft_score(m)
    if score >= SCORE_B_THRESHOLD:
        decision = RouteDecision(
            route="B",
            soft_score=score,
            soft_hits=hits,
            metrics=metrics_log,
        )
        _LAST_ROUTE = decision
        return decision

    decision = RouteDecision(
        route="A",
        soft_score=score,
        soft_hits=hits,
        metrics=metrics_log,
    )
    _LAST_ROUTE = decision
    return decision


def trial_full_text(trial_chunks: list[Chunk]) -> str:
    """路径 B 用的全文：试切各节正文按序拼接（含 toc 文本，保持阅读序）。"""
    parts = [(c.text or "").strip() for c in trial_chunks if (c.text or "").strip()]
    return "\n\n".join(parts)
