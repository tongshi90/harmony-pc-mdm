"""
RAG 轻量 LLM 客户端（问题改写 / 子问题拆分）。

Key / URL / 模型名一律来自 ``app.config.settings``（在线模型段），本文件不另存默认厂商地址。
Embedding / Rerank / 主生成见 ``app.rag.lightrag_engine``；图片 VL 见 ``splitter.pdf.image_vl``。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import requests

from app.config import settings

logger = logging.getLogger("mdm.rag.model")


def get_config(key: str, default: Optional[str] = None) -> str:
    mapping = {
        "SILICONFLOW_API_KEY": settings.rag_siliconflow_api_key,
        "SILICONFLOW_CHAT_URL": settings.rag_chat_url,
        "SILICONFLOW_CHAT_MODEL": settings.rag_chat_model,
        "SILICONFLOW_TEXT_SPLITTER_MODEL": settings.rag_text_splitter_model,
    }
    if key in mapping:
        val = mapping[key]
        if val is None or val == "":
            if default is not None:
                return default
            raise ValueError(f"RAG 配置项 '{key}' 未设置（见 app.config Settings）")
        return str(val)
    if default is not None:
        return default
    raise ValueError(f"未知 RAG 配置项: {key}")


def get_int_config(key: str, default: int = 0) -> int:
    mapping = {
        "CHAT_TIMEOUT": settings.rag_chat_timeout,
        "CHAT_MAX_TOKENS": settings.rag_chat_max_tokens,
        "TEXT_SPLITTER_TIMEOUT": settings.rag_text_splitter_timeout,
    }
    if key in mapping:
        return int(mapping[key])
    return default


def get_float_config(key: str, default: float = 0.0) -> float:
    mapping = {
        "CHAT_TEMPERATURE": settings.rag_chat_temperature,
        "TEXT_SPLITTER_TEMPERATURE": settings.rag_text_splitter_temperature,
    }
    if key in mapping:
        return float(mapping[key])
    return default


class ChatModel(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        pass


class SiliconFlowChat(ChatModel):
    def __init__(self, model: Optional[str] = None) -> None:
        self.api_key = get_config("SILICONFLOW_API_KEY")
        self.api_url = get_config("SILICONFLOW_CHAT_URL")
        self.model = model or get_config("SILICONFLOW_CHAT_MODEL")
        self.timeout = get_int_config("CHAT_TIMEOUT", 60)
        self.max_tokens = get_int_config("CHAT_MAX_TOKENS", 4096)
        self.temperature = get_float_config("CHAT_TEMPERATURE", 0.7)

    def chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "temperature": kwargs.get("temperature", self.temperature),
            }
            response = requests.post(
                self.api_url, headers=headers, json=payload, timeout=self.timeout
            )
            if response.status_code == 200:
                result = response.json()
                return (
                    result.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
            logger.warning("Chat API error: %s %s", response.status_code, response.text)
            return f"聊天API调用失败: {response.status_code}"
        except Exception as e:
            logger.exception("Chat API call error")
            return f"聊天API调用异常: {e}"


def get_text_splitter_llm() -> ChatModel:
    return SiliconFlowChat(model=get_config("SILICONFLOW_TEXT_SPLITTER_MODEL"))
