"""
RAG 模块本地路径（上传文件、LightRAG 存储等）。

与主库 data/mdm.db 分离：RAG 大文件落在 data/rag/ 下。
向量与切片由 LightRAG（NanoVectorDB + JsonKV）按知识库 workspace 持久化。
"""

from __future__ import annotations

from pathlib import Path

from app.config import DATA_DIR, settings

# data/rag/ 根目录（可用 MDM_RAG_DATA_DIR 覆盖相对/绝对路径）
_rag_dir_cfg = (settings.rag_data_dir or "").strip()
if _rag_dir_cfg:
    RAG_DATA_DIR = Path(_rag_dir_cfg)
    if not RAG_DATA_DIR.is_absolute():
        RAG_DATA_DIR = DATA_DIR / _rag_dir_cfg
else:
    RAG_DATA_DIR = DATA_DIR / "rag"

UPLOAD_PATH = RAG_DATA_DIR / "upload"
LIGHTRAG_PATH = RAG_DATA_DIR / "lightrag"


def get_lightrag_root(env_path: str | None = None) -> str:
    """LightRAG 根目录；其下按 kb_{id} 分子目录。"""
    if env_path:
        return env_path
    override = (settings.rag_lightrag_dir or "").strip()
    if override:
        p = Path(override)
        return str(p if p.is_absolute() else DATA_DIR / p)
    return str(LIGHTRAG_PATH)


def get_upload_path(env_path: str | None = None) -> str:
    if env_path:
        return env_path
    override = (settings.rag_upload_dir or "").strip()
    if override:
        p = Path(override)
        return str(p if p.is_absolute() else DATA_DIR / p)
    return str(UPLOAD_PATH)


def ensure_rag_dirs() -> None:
    RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_PATH.mkdir(parents=True, exist_ok=True)
    LIGHTRAG_PATH.mkdir(parents=True, exist_ok=True)
    (LIGHTRAG_PATH / "inputs").mkdir(parents=True, exist_ok=True)


ensure_rag_dirs()
